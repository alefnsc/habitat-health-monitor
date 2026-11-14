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
from hub.timeutil import parse_iso, to_iso

WINDOW = timedelta(hours=24)
EARTH_G = 9.81


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


# Training work for the same window (NU10). Mechanical work on the load, never converted to or
# compared with food energy: this module holds no energy constant.


def exercise_day(store, crew: str | None, at: datetime) -> dict:
    from hub.exercise import Session, align, latest_reps, work_cell_j

    start = at - WINDOW
    in_window = store.reps_between(start, at)
    rows = {r[0]: r for r in store.session_rows()}

    def crew_of(session: str) -> str | None:
        row = rows.get(session)
        return row[3] if row else None

    def wanted(session: str) -> bool:
        return crew is None or crew_of(session) == crew

    by_session: dict[str, list] = {}
    for r in in_window:
        if wanted(r.session):
            by_session.setdefault(r.session, []).append(r)
    sessions = sum(
        1 for row in rows.values() if start < parse_iso(row[4]) <= at and wanted(row[0])
    )  # fmt: skip
    camera_reps = 0
    excluded = 0
    camera_work: list[float] = []
    cell_work: list[float] = []
    replay = False
    for sid, reps in by_session.items():
        cam = latest_reps([r for r in reps if r.src == "camera"])
        cel = [r for r in reps if r.src == "load_cell"]
        earth = [r for r in cam if r.g == EARTH_G]
        excluded += len(cam) - len(earth)
        camera_reps += len(earth)
        camera_work += [r.work_j for r in earth if r.work_j is not None]
        replay = replay or any(r.node == "sim-1" for r in earth)
        row = rows.get(sid)
        if row is not None:
            sess = Session(row[0], row[1], row[2], row[3], row[4], row[5], 0, 0)
            for _n, c, lc in align(earth, cel):
                w = work_cell_j(store, sess, lc, c)
                if w is not None:
                    cell_work.append(w)
    return {
        "window_start": to_iso(start),
        "window_end": to_iso(at),
        "sessions": sessions,
        "camera_reps": camera_reps,
        "camera_work_j": sum(camera_work) if camera_reps and camera_work else None,
        "cell_work_j": sum(cell_work) if cell_work else None,
        "replay": replay,
        "excluded_reps": excluded,
    }
