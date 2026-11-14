"""Link configuration: light time, time scale and scheduled blackouts (spec 5.9)."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

MAX_LIGHT_TIME_S = 1400.0  # Mars one-way maximum is about 1,338 s


class ConfigError(Exception):
    """Raised when the link file is missing a field or holds an invalid value."""


@dataclass(frozen=True)
class Blackout:
    """Scheduled blackout in wall-clock seconds after linksim start (half-open)."""

    start: float
    end: float


@dataclass(frozen=True)
class LinkConfig:
    light_time_s: float
    time_scale: float
    blackouts: list[Blackout] = field(default_factory=list)


def _number(data: dict, key: str) -> float:
    if key not in data:
        raise ConfigError(f"{key} is required")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number")
    return float(value)


def load_config(path: Path) -> LinkConfig:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read link file: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("link file must be a JSON object")

    light = _number(data, "light_time_s")
    if not 0 <= light <= MAX_LIGHT_TIME_S:
        raise ConfigError(f"light_time_s must be between 0 and {MAX_LIGHT_TIME_S:g}")
    scale = _number(data, "time_scale")
    if scale < 1:
        raise ConfigError("time_scale must be at least 1")

    raw = data.get("blackouts", [])
    if not isinstance(raw, list):
        raise ConfigError("blackouts must be a list")
    blackouts: list[Blackout] = []
    for i, b in enumerate(raw):
        try:
            start, end = float(b["start"]), float(b["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"blackouts[{i}] needs numeric start and end") from exc
        if start < 0 or end <= start:
            raise ConfigError(f"blackouts[{i}] must have 0 <= start < end")
        blackouts.append(Blackout(start, end))
    blackouts.sort(key=lambda b: b.start)
    for prev, nxt in itertools.pairwise(blackouts):
        if nxt.start < prev.end:
            raise ConfigError("blackouts overlap")
    return LinkConfig(light, scale, blackouts)


def hold_seconds(cfg: LinkConfig) -> float:
    return cfg.light_time_s / cfg.time_scale


def in_blackout(cfg: LinkConfig, elapsed_s: float) -> Blackout | None:
    for b in cfg.blackouts:
        if b.start <= elapsed_s < b.end:
            return b
    return None
