"""Thresholds loader and band evaluation (spec 4.8, D13, NU8)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any, Literal

from hub.contract import DERIVED, INDICATORS

log = logging.getLogger("hub.thresholds")

WINDOWS: frozenset[str] = frozenset(
    {"instant", "mean_1h", "mean_7d", "dose_24h", "cumulative", "sum_24h_floor"}
)
SOURCE_KINDS: frozenset[str] = frozenset(
    {"nasa_std", "nasa_doc", "clinical_ref", "personal_baseline", "team_convention"}
)
_BAND_KEYS = frozenset({"min", "max", "lt", "gt"})


class ThresholdsError(ValueError):
    pass


@dataclass(frozen=True)
class Band:
    min: float | None = None
    max: float | None = None
    lt: float | None = None
    gt: float | None = None

    def contains(self, x: float) -> bool:
        if self.min is not None and x < self.min:
            return False
        if self.max is not None and x > self.max:
            return False
        if self.lt is not None and not x < self.lt:
            return False
        return not (self.gt is not None and not x > self.gt)


@dataclass(frozen=True)
class Hours:
    start: time
    end: time

    def contains(self, local: time) -> bool:
        if self.start <= self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end


@dataclass(frozen=True)
class Rule:
    id: str
    ind: str
    window: str
    ok: Band | None
    watch: Band | None
    act: Band | None
    source_kind: str
    source_ref: str
    url: str
    note: str
    hours: Hours | None
    order: int


def _band(rule_id: str, name: str, raw: Any) -> Band | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ThresholdsError(f"rule {rule_id}: band {name} must be an object")
    extra = set(raw) - _BAND_KEYS
    if extra:
        raise ThresholdsError(f"rule {rule_id}: band {name} has unknown key {min(extra)}")
    vals: dict[str, float | None] = {}
    for k in _BAND_KEYS:
        v = raw.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            raise ThresholdsError(f"rule {rule_id}: band {name} key {k} must be a number")
        vals[k] = None if v is None else float(v)
    if vals["min"] is not None and vals["max"] is not None and vals["min"] > vals["max"]:
        raise ThresholdsError(f"rule {rule_id}: band {name} has min > max")
    return Band(min=vals["min"], max=vals["max"], lt=vals["lt"], gt=vals["gt"])


def _hhmm(rule_id: str, raw: Any) -> time:
    try:
        hh, mm = str(raw).split(":")
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        raise ThresholdsError(f"rule {rule_id}: bad hours value {raw!r}") from None


def _hours(rule_id: str, raw: Any) -> Hours | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or "start" not in raw or "end" not in raw:
        raise ThresholdsError(f"rule {rule_id}: hours needs start and end")
    return Hours(_hhmm(rule_id, raw["start"]), _hhmm(rule_id, raw["end"]))


def _rule(raw: Any, order: int) -> Rule:
    if not isinstance(raw, dict):
        raise ThresholdsError(f"rule #{order} is not an object")
    rid = raw.get("id")
    if not isinstance(rid, str) or not rid:
        raise ThresholdsError(f"rule #{order} has no id")
    for f in ("ind", "window", "source_kind", "source_ref"):
        if not isinstance(raw.get(f), str) or not raw[f]:
            raise ThresholdsError(f"rule {rid}: missing {f}")
    if raw["window"] not in WINDOWS:
        raise ThresholdsError(f"rule {rid}: unknown window {raw['window']!r}")
    if raw["source_kind"] not in SOURCE_KINDS:
        raise ThresholdsError(f"rule {rid}: unknown source_kind {raw['source_kind']!r}")
    ok, watch, act = (_band(rid, n, raw.get(n)) for n in ("ok", "watch", "act"))
    if ok is None and watch is None and act is None:
        raise ThresholdsError(f"rule {rid}: needs at least one of ok, watch, act")
    if raw["ind"] not in INDICATORS and raw["ind"] not in DERIVED:
        log.warning("rule %s names unknown indicator %s", rid, raw["ind"])
    return Rule(
        id=rid, ind=raw["ind"], window=raw["window"], ok=ok, watch=watch, act=act,
        source_kind=raw["source_kind"], source_ref=raw["source_ref"],
        url=str(raw.get("url") or ""), note=str(raw.get("note") or ""),
        hours=_hours(rid, raw.get("hours")), order=order,
    )  # fmt: skip


def parse_rules(data: Any) -> list[Rule]:
    if not isinstance(data, list):
        raise ThresholdsError("thresholds file must hold a list of rules")
    rules = [_rule(raw, i) for i, raw in enumerate(data)]
    _check_unique(rules)
    return rules


def _check_unique(rules: list[Rule]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for r in rules:
        key = (r.id, r.ind, r.window)
        if key in seen:
            raise ThresholdsError(f"duplicate rule {r.id} for {r.ind}/{r.window}")
        seen.add(key)


def load_rules(path: Path) -> list[Rule]:
    path = Path(path)
    if not path.exists():
        log.warning("thresholds file not found: %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ThresholdsError(f"{path}: invalid JSON: {e}") from None
    return parse_rules(data)


def load_rule_files(paths: list[Path]) -> list[Rule]:
    rules: list[Rule] = []
    for p in paths:
        rules.extend(load_rules(p))
    rules = [Rule(**{**r.__dict__, "order": i}) for i, r in enumerate(rules)]
    _check_unique(rules)
    return rules


def band_status(rule: Rule, x: float) -> Literal["ok", "watch", "act", "unknown"]:
    for name in ("ok", "watch", "act"):
        band: Band | None = getattr(rule, name)
        if band is not None and band.contains(x):
            return name  # type: ignore[return-value]
    return "unknown"


def rules_for(rules: list[Rule], ind: str) -> list[Rule]:
    return [r for r in rules if r.ind == ind]
