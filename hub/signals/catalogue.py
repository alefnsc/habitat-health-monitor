"""The v1 signal catalogue as data (D45 §7). The engine dispatches on (kind, source)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from hub.signals.types import Kind

MIN = timedelta(minutes=1)
H = timedelta(hours=1)
D = timedelta(days=1)

INDEPENDENCE = "signals.limit.independence"
BENCH = "signals.limit.benchSensor"
STRAIGHT = "signals.limit.straightLine"
RING = "signals.limit.ringEstimate"
REST_ONLY = "signals.limit.restOnly"
OWN_DATA = "signals.limit.ownData"
ISS = "signals.limit.issTelemetry"
EARTH = "signals.limit.earthReference"
NEIGHBOUR_HOURS = "signals.limit.neighbourHours"
CAMERA = "signals.limit.cameraEstimate"
NOT_FOOD = "signals.limit.notFoodEnergy"
RIG_CHECK = "signals.limit.rigCheck"
ON_EARTH = "signals.limit.onEarth"
LOGGED_ONLY = "signals.limit.loggedOnly"


@dataclass(frozen=True)
class Spec:
    id: str
    kind: Kind
    source: str  # "cabin", "cabin_mean_1h", "night_rest_hr", "night_value", ...
    ind: str | None
    window: timedelta
    block: timedelta | None
    min_n: int
    coverage: float  # share of expected blocks (or days) that must be present
    per_crew: bool  # True: one signal per crew; False: crew None (cabin, ISS, Earth)
    can_trigger: bool = False
    rule_id: str | None = None
    side: str = "both"  # baseline: which side of the range counts as notable
    limits: tuple[str, ...] = ()
    unit: str | None = None  # when the value is not in the indicator's own unit


CATALOGUE: tuple[Spec, ...] = (
    Spec("cabin_temp_6h", "trend", "cabin", "cabin_temp", 6 * H, 10 * MIN, 10, 0.75, False,
         limits=(INDEPENDENCE, BENCH)),
    Spec("cabin_rh_6h", "trend", "cabin", "cabin_rh", 6 * H, 10 * MIN, 10, 0.75, False,
         limits=(INDEPENDENCE, BENCH)),
    Spec("cabin_temp_ttl", "time_to_limit", "cabin", "cabin_temp", 2 * H, 5 * MIN, 18, 0.75, False,
         can_trigger=True, rule_id="cabin_health_box_temp", limits=(STRAIGHT, BENCH)),
    Spec("cabin_rh_ttl", "time_to_limit", "cabin", "cabin_rh", 2 * H, 5 * MIN, 18, 0.75, False,
         can_trigger=True, rule_id="cabin_health_box_rh", limits=(STRAIGHT, BENCH)),
    Spec("cabin_ppco2_ttl", "time_to_limit", "cabin_mean_1h", "cabin_ppco2", 2 * H, 5 * MIN, 18,
         0.75, False, can_trigger=True, rule_id="co2_1h", limits=(STRAIGHT,)),
    Spec("rest_hr_baseline", "baseline", "night_rest_hr", "hr", 14 * D, None, 7, 0.0, True,
         can_trigger=True, limits=(RING, REST_ONLY)),
    Spec("rest_hr_14n", "trend", "night_rest_hr", "hr", 14 * D, None, 10, 0.75, True,
         limits=(INDEPENDENCE, RING, REST_ONLY)),
    Spec("sleep_baseline", "baseline", "night_value", "sleep_h", 14 * D, None, 7, 0.0, True,
         can_trigger=True, limits=(RING,)),
    Spec("spo2_baseline", "baseline", "night_value", "spo2", 14 * D, None, 7, 0.0, True,
         can_trigger=True, side="low", limits=(RING,)),
    # slice 3: ISS Live stored as readings
    # 30-minute blocks: ISS Live pushes a value only when it changes (team owner, 2026-11-15).
    Spec("iss_ppco2_6h", "trend", "cabin", "iss_ppco2", 6 * H, 30 * MIN, 10, 0.75, False,
         limits=(INDEPENDENCE, ISS)),
)  # fmt: skip

BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
