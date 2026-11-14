"""Tilt witness (D39): when the sealed tilt switch rose and fell around a camera rep.

The switch trips when the weight tilts past its trip angle and releases when it comes back,
so in a rep it rises (0 -> 1) in the lift and falls (1 -> 0) in the lowering. The witness is
the rise -> fall pair whose midpoint is nearest the camera turnaround. Computed on read: a
tilt change can arrive after the rep message.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hub.store import Store, StoredRep
from hub.timeutil import parse_iso, to_iso

TILT_NODE = "tilt-1"
WINDOW_MS = 500
LOOKBACK_MS = 15000  # longer than the 10 s heartbeat, so the state before the window is known


@dataclass(frozen=True)
class Change:
    at: datetime
    val: int  # 1 = rise (tripped), 0 = fall (released)


def tilt_changes(rows: Iterable[Any]) -> list[Change]:
    """Value changes of tilt-1 readings in time order. Repeated values (heartbeats) are not
    changes; the first reading only sets the starting state."""
    mine = sorted((r for r in rows if r.node == TILT_NODE), key=lambda r: (r.measured_at, r.id))
    out: list[Change] = []
    prev: int | None = None
    for r in mine:
        v = 1 if r.val >= 0.5 else 0
        if prev is not None and v != prev:
            out.append(Change(parse_iso(r.measured_at), v))
        prev = v
    return out


def _mid(rise: datetime, fall: datetime) -> datetime:
    return rise + (fall - rise) / 2


def tilt_witness(
    changes: list[Change],
    t0: datetime,
    t1: datetime,
    turn: datetime,
    window_ms: int = WINDOW_MS,
) -> dict:
    lo, hi = t0 - timedelta(milliseconds=window_ms), t1 + timedelta(milliseconds=window_ms)
    inside = [c for c in changes if lo <= c.at <= hi]
    pairs: list[tuple[datetime, datetime]] = []
    for i, c in enumerate(inside):
        if c.val != 1:
            continue
        fall = next((d for d in inside[i + 1 :] if d.val == 0), None)
        if fall is not None:
            pairs.append((c.at, fall.at))
    if not pairs:
        return {"seen": False, "turn_inside": False, "offset_ms": None, "rise_at": None,
                "fall_at": None}  # fmt: skip
    rise, fall = min(pairs, key=lambda p: abs((_mid(*p) - turn).total_seconds()))
    offset = round((_mid(rise, fall) - turn).total_seconds() * 1000)
    return {
        "seen": True,
        "turn_inside": rise <= turn <= fall,
        "offset_ms": offset,
        "rise_at": to_iso(rise),
        "fall_at": to_iso(fall),
    }


def tilt_for_rep(store: Store, rep: StoredRep) -> dict | None:
    """Witness for one camera rep, or None when the rep carries no turnaround."""
    if rep.t_turn_ms is None:
        return None
    t1 = parse_iso(rep.measured_at)  # the camera anchors age_ms on t1
    t0 = t1 - timedelta(milliseconds=rep.t1_ms - rep.t0_ms)
    turn = t1 - timedelta(milliseconds=rep.t1_ms - rep.t_turn_ms)
    rows = store.readings_between(
        "tilt",
        t0 - timedelta(milliseconds=WINDOW_MS + LOOKBACK_MS),
        t1 + timedelta(milliseconds=WINDOW_MS),
        include_start=True,
    )
    return tilt_witness(tilt_changes(rows), t0, t1, turn)
