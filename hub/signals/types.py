"""The Signal object (D45 §5). Text is never built here: the console turns keys into words."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Kind = Literal["trend", "baseline", "time_to_limit", "lagged_pair"]
State = Literal["notable", "steady", "not_enough_data"]


@dataclass(frozen=True)
class Input:
    ind: str
    src: str
    dev: str
    node: str
    n: int
    first_at: str
    last_at: str
    oldest_age_s: float


@dataclass(frozen=True)
class Value:
    estimate: float
    low: float
    high: float
    unit: str
    per: str | None = None


@dataclass(frozen=True)
class Method:
    name: str
    ref: str
    alpha: float | None
    n: int
    min_n: int
    window_start: str
    window_end: str
    coverage: float | None


@dataclass(frozen=True)
class Missing:
    key: str
    need: int | None = None
    have: int | None = None


@dataclass(frozen=True)
class Signal:
    id: str
    kind: Kind
    crew: str | None
    state: State
    headline_key: str
    value: Value | None
    method: Method
    inputs: list[Input] = field(default_factory=list)
    missing: list[Missing] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    reference: dict | None = None
    replay: bool = False
    series: list[list] = field(default_factory=list)  # [[iso time, value], ...] blocked points
    pairs: list[list] = field(default_factory=list)  # lagged pairs only: [[key, x, y], ...]
    can_trigger: bool = False
    detail: dict = field(default_factory=dict)  # kind-specific extras, e.g. one entry per lag

    def to_dict(self) -> dict:
        return asdict(self)
