"""Assessment engine: window values, bands, hours, coverage, alerts, preview (H7a, H7b)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from hub.contract import BODY_INDS, DERIVED, INDICATORS, INTAKE_INDS
from hub.results import Alert, AssessmentResult, entry_for, escalate_to_for
from hub.store import Store, StoredReading
from hub.thresholds import Rule, band_status, rules_for
from hub.timeutil import parse_iso, to_iso

log = logging.getLogger("hub.assess")

CREW_SCOPED = BODY_INDS | INTAKE_INDS
UNGATED_INDS = frozenset({"motion", "load_raw", "tilt"})
ESCALATIONS = frozenset({"self", "cmo", "flight_surgeon"})
_COVERAGE_S = {"mean_1h": 2700, "mean_7d": 86400, "sum_24h_floor": 72000}
_WINDOW_S = {"mean_1h": 3600, "mean_7d": 7 * 86400, "dose_24h": 86400, "sum_24h_floor": 86400}


def coverage_ok(window: str, span_s: float) -> bool:
    return span_s >= _COVERAGE_S.get(window, 0)


def guidance_id_for(rule_id: str, status: str) -> str:
    return f"{rule_id}.{status}"


def load_escalation(path: Path) -> dict[str, str]:
    """guidance_id -> escalate_to, read from the `id` and `escalate_to` of each item."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        log.warning("guidance file is not valid JSON: %s", path)
        return {}
    if isinstance(data, dict):
        data = data.get("items") or data.get("guidance") or []
    out: dict[str, str] = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or "id" not in item or "escalate_to" not in item:
            continue
        if item["escalate_to"] not in ESCALATIONS:
            log.warning("guidance %s has bad escalate_to %r", item["id"], item["escalate_to"])
            continue
        out[str(item["id"])] = item["escalate_to"]
    return out


class Assessor:
    def __init__(
        self,
        store: Store,
        rules: list[Rule],
        *,
        tz: str,
        escalation: dict[str, str] | None = None,
        emit: Callable[[str, dict], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.store = store
        self.rules = rules
        self.tz = ZoneInfo(tz)
        self.escalation = escalation or {}
        self.emit = emit
        self._alert_cbs: list[Callable[[Alert], None]] = []

    # window values

    def _window_value(
        self, rule: Rule, ind: str, crew: str | None, at: datetime
    ) -> tuple[float | None, float]:
        """(value, coverage seconds) of a non-instant rule over the window ending at `at`."""
        scope = ind in CREW_SCOPED
        span = _WINDOW_S.get(rule.window)
        start = at - timedelta(seconds=span) if span else None
        fn = "avg" if rule.window.startswith("mean") else "sum"
        val, n, first = self.store.window_aggregate(ind, start, at, crew, scope, fn)
        if n == 0 or first is None:
            return None, 0.0
        return val, (at - parse_iso(first)).total_seconds()

    def _evaluate(
        self,
        rule: Rule,
        *,
        ind: str,
        unit: str,
        crew: str | None,
        at: datetime,
        measured_at: str,
        reading_id: int,
        own_val: float | None,
    ) -> AssessmentResult:
        if rule.window == "instant":
            val, covered = own_val, True
        else:
            val, cov_s = self._window_value(rule, ind, crew, at)
            covered = coverage_ok(rule.window, cov_s)
        status = "unknown"
        if val is not None and covered:
            status = band_status(rule, val)
        if status == "unknown":
            escalate = "self"
        else:
            gid = guidance_id_for(rule.id, status)
            escalate = self.escalation.get(gid) or escalate_to_for(status, ind)
        return AssessmentResult(
            id=0,
            reading_id=reading_id,
            ind=ind,
            val=val,
            unit=unit,
            status=status,
            rule_id=rule.id,
            source_kind=rule.source_kind,
            source_ref=rule.source_ref,
            guidance_id=guidance_id_for(rule.id, status),
            escalate_to=escalate,
            measured_at=measured_at,
            crew=crew,
        )

    def _active(self, rule: Rule, at: datetime) -> bool:
        return rule.hours is None or rule.hours.contains(at.astimezone(self.tz).time())

    # assess a stored reading

    def assess(self, r: StoredReading) -> tuple[list[AssessmentResult], list[Alert]]:
        if r.q != ("ok",) or r.ind in UNGATED_INDS:
            return [], []
        at = parse_iso(r.measured_at)
        rules = rules_for(self.rules, r.ind)
        results: list[AssessmentResult] = []
        alerts: list[Alert] = []
        if not rules:
            results.append(
                self.store.insert_assessment(
                    AssessmentResult(
                        id=0,
                        reading_id=r.id,
                        ind=r.ind,
                        val=r.val,
                        unit=r.unit,
                        status="unknown",
                        rule_id=None,
                        source_kind=None,
                        source_ref=None,
                        guidance_id=None,
                        escalate_to="self",
                        measured_at=r.measured_at,
                        crew=r.crew,
                    )
                )
            )
            return results, []
        for rule in rules:
            if not self._active(rule, at):
                continue
            res = self._evaluate(
                rule,
                ind=r.ind,
                unit=r.unit,
                crew=r.crew,
                at=at,
                measured_at=r.measured_at,
                reading_id=r.id,
                own_val=r.val,
            )
            prev = self.store.last_status(rule.id, r.ind, r.crew)
            res = self.store.insert_assessment(res)
            results.append(res)
            fires = res.status != "unknown" and res.status != prev
            if fires and (prev is not None or res.status in ("watch", "act")):
                alerts.append(
                    Alert(
                        id=res.id,
                        ind=res.ind,
                        status=res.status,
                        prev_status=prev,
                        rule_id=rule.id,
                        measured_at=res.measured_at,
                        crew=res.crew,
                        escalate_to=res.escalate_to,
                    )
                )
        return results, alerts

    def on_alert(self, cb: Callable[[Alert], None]) -> None:
        self._alert_cbs.append(cb)

    def publish_alerts(self, alerts: list[Alert]) -> None:
        """Outbox, emit and call back, in that order, for each alert."""
        for a in alerts:
            self.store.append_outbox("alert", a.to_dict(), self.clock())
            if self.emit is not None:
                self.emit("alert", a.to_dict())
            log.info("alert %s %s prev=%s", a.rule_id, a.status, a.prev_status)
            for cb in self._alert_cbs:
                try:
                    cb(a)
                except Exception:
                    log.exception("alert callback failed")

    # live preview (NU7): nothing stored, alerted or emitted

    def preview(self, ind: str, crew: str | None, at: datetime) -> list[AssessmentResult]:
        unit = INDICATORS.get(ind) or DERIVED.get(ind, "")
        at_iso = to_iso(at)
        rules = rules_for(self.rules, ind)
        if not rules:
            return [
                AssessmentResult(
                    id=0,
                    reading_id=0,
                    ind=ind,
                    val=None,
                    unit=unit,
                    status="unknown",
                    rule_id=None,
                    source_kind=None,
                    source_ref=None,
                    guidance_id=None,
                    escalate_to="self",
                    measured_at=at_iso,
                    crew=crew,
                )
            ]
        out = []
        for rule in rules:
            if not self._active(rule, at):
                continue
            out.append(
                self._evaluate(
                    rule,
                    ind=ind,
                    unit=unit,
                    crew=crew,
                    at=at,
                    measured_at=at_iso,
                    reading_id=0,
                    own_val=None,
                )
            )
        return out


def status_body(store: Store, nodes: list[dict], crew: str | None, now: datetime) -> dict:
    """GET /api/status body (D2): one worst-of entry per indicator that has any reading."""
    results = []
    for ind in [*INDICATORS, *DERIVED]:
        scoped = crew is not None and ind in CREW_SCOPED
        r = store.latest_reading(ind, crew=crew, scope_crew=scoped)
        if r is None:
            continue
        results.append(entry_for(r, store.results_for(r.id)).to_dict())
    return {"crew": crew, "generated_at": to_iso(now), "nodes": nodes, "results": results}
