"""Rolling 24 h food totals (NU7). Pure builders: inputs are passed in, so tests need no app.

Assumed interfaces from the H agent (H7a, H19), build-time fakes in the tests:
- `assessor.preview(ind, crew, at) -> list[AssessmentResult]` (nothing stored)
- `store.meals_between(start, end, crew) -> list[row]`; crew None means every crew
- `rules`: the loaded `hub.thresholds.Rule` list (to find which rules use `sum_24h_floor`)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any

from hub.contract import INTAKE_ORDER
from hub.results import SEVERITY
from hub.timeutil import to_iso

WINDOW = timedelta(hours=24)


def _worst(results: list) -> Any | None:
    best = None
    for r in results:
        if best is None or SEVERITY[r.status] > SEVERITY[best.status]:
            best = r
    return best


def _total(
    store, assessor, rules, ind: str, crew: str | None, at: datetime, crews: Sequence[str],
    meals_total: int,
) -> dict:  # fmt: skip
    start = at - WINDOW
    rows = store.readings_between(ind, start, at, crew=crew, scope_crew=crew is not None)
    val = sum(r.val for r in rows) if rows else None
    floor_ids = {r.id for r in rules if r.ind == ind and r.window == "sum_24h_floor"}
    scopes = [crew] if crew is not None else list(crews)
    results = [res for c in scopes for res in assessor.preview(ind, c, at)]
    worst = _worst(results)
    status = worst.status if worst is not None and rows else "unknown"
    floor_judged: bool | None = None
    if floor_ids:
        by_scope = [
            any(r.rule_id in floor_ids and r.status != "unknown" for r in assessor.preview(ind, c, at))
            for c in scopes
        ]  # fmt: skip
        floor_judged = bool(by_scope) and all(by_scope)
    keep = worst is not None and status != "unknown"
    return {
        "val": val,
        "meals_reporting": len(rows),
        "meals_total": meals_total,
        "status": status,
        "rule_id": worst.rule_id if keep else None,
        "source_kind": worst.source_kind if keep else None,
        "source_ref": worst.source_ref if keep else None,
        "escalate_to": worst.escalate_to if keep else "self",
        "floor_judged": floor_judged,
    }


def _meal_dict(m: Any) -> Any:
    if hasattr(m, "to_dict"):
        return m.to_dict()
    return asdict(m) if is_dataclass(m) else m


def food_day(
    store, assessor, crew: str | None, at: datetime, *, crews: Sequence[str], rules: Sequence = ()
) -> dict:  # fmt: skip
    start = at - WINDOW
    meals = store.meals_between(start, at, crew)
    totals = {
        ind: _total(store, assessor, rules, ind, crew, at, crews, len(meals))
        for ind in INTAKE_ORDER
    }
    mass = store.latest_reading("body_mass", crew=crew, scope_crew=crew is not None)
    return {
        "crew": crew,
        "window_start": to_iso(start),
        "window_end": to_iso(at),
        "totals": totals,
        "meals": [_meal_dict(m) for m in meals],
        "body_mass": mass.val if mass else None,
    }
