"""Signals computed on read (D45 §4.1). evaluate() never writes to the store."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from hub.signals import body, cabin, daily, lift, pairs
from hub.signals.catalogue import BY_ID, CATALOGUE, Spec
from hub.signals.common import Ctx
from hub.signals.types import Signal
from hub.store import Store
from hub.thresholds import Rule

log = logging.getLogger("hub.signals")

Builder = Callable[[Ctx, Spec, str | None], Signal]
BUILDERS: dict[tuple[str, str], Builder] = {
    ("trend", "cabin"): cabin.cabin_trend,
    ("time_to_limit", "cabin"): cabin.time_to_limit,
    ("time_to_limit", "cabin_mean_1h"): cabin.time_to_limit,
    ("baseline", "night_rest_hr"): body.baseline,
    ("baseline", "night_value"): body.baseline,
    ("trend", "night_rest_hr"): body.night_trend,
    ("trend", "daily_last"): daily.daily_trend,
    ("trend", "daily_sum"): daily.daily_trend,
    ("trend", "lift_sets"): lift.work_across_sets,
    ("trend", "lift_within"): lift.work_within_set,
    ("baseline", "lift_tilt"): lift.tilt_agreement,
    ("lagged_pair", "cabin_earth"): pairs.cabin_vs_earth,
    ("lagged_pair", "training_rest_hr"): pairs.training_vs_rest_hr,
    ("lagged_pair", "meal_sleep"): pairs.last_meal_vs_sleep,
    ("lagged_pair", "space_weather_sleep"): pairs.space_weather_vs_sleep,
}


def evaluate_spec(ctx: Ctx, spec: Spec, crew: str | None) -> Signal | None:
    """One signal, or None when its builder failed (logged; the other signals are unaffected)."""
    try:
        return BUILDERS[(spec.kind, spec.source)](ctx, spec, crew if spec.per_crew else None)
    except Exception:
        log.exception("signal %s failed for crew %s", spec.id, crew)
        return None


def evaluate(
    store: Store, rules: Sequence[Rule], *, crews: Sequence[str], at: datetime, tz: str,
    ids: Sequence[str] | None = None,
) -> list[Signal]:  # fmt: skip
    """Cabin signals once (crew None), body signals once per crew in `crews`, in catalogue order."""
    ctx = Ctx(store, {r.id: r for r in rules}, at, ZoneInfo(tz))
    specs = [BY_ID[i] for i in ids] if ids is not None else list(CATALOGUE)
    out: list[Signal] = []
    for spec in specs:
        for crew in crews if spec.per_crew else [None]:
            s = evaluate_spec(ctx, spec, crew)
            if s is not None:
                out.append(s)
    return out
