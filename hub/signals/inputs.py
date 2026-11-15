"""Store rows to the series the methods take (D45 §6.5). Only assessable rows; no gap is filled.

Replay and real rows never pool: `choose` keeps the real rows when any exist in the window, and the
replay rows only when the window has no real row.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from hub.assess import CREW_SCOPED
from hub.signals.types import Input
from hub.store import Store, StoredReading
from hub.timeutil import parse_iso, to_iso

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def ok_rows(
    store: Store, ind: str, start: datetime, end: datetime, crew: str | None
) -> list[StoredReading]:
    """Assessable rows of `ind` in (start, end], crew-scoped like the assessor."""
    rows = store.readings_between(ind, start, end, crew=crew, scope_crew=ind in CREW_SCOPED)
    return [r for r in rows if r.q == ("ok",)]


def choose(rows: Sequence[StoredReading]) -> tuple[list[StoredReading], bool]:
    """(rows to use, replay flag): the real rows if any exist, else the replay rows."""
    real = [r for r in rows if r.src != "replay"]
    if real:
        return real, False
    return list(rows), bool(rows)


def same_mode(rows: Sequence[StoredReading], replay: bool) -> list[StoredReading]:
    """Keep only rows of the chosen mode, so a second input follows the first input's choice."""
    return [r for r in rows if (r.src == "replay") == replay]


def describe(rows: Iterable[StoredReading], at: datetime) -> list[Input]:
    """One Input per (ind, src, dev, node) group, in first-seen order."""
    groups: dict[tuple[str, str, str, str], list[StoredReading]] = {}
    for r in rows:
        groups.setdefault((r.ind, r.src, r.dev, r.node), []).append(r)
    out = []
    for (ind, src, dev, node), rs in groups.items():
        times = sorted(r.measured_at for r in rs)
        oldest = (at - parse_iso(times[-1])).total_seconds()
        out.append(Input(ind, src, dev, node, len(rs), times[0], times[-1], max(0.0, oldest)))
    return out


def points(rows: Iterable[StoredReading]) -> list[tuple[datetime, float]]:
    return [(parse_iso(r.measured_at), r.val) for r in rows]


def block_medians(
    pts: Sequence[tuple[datetime, float]], start: datetime, end: datetime, block: timedelta
) -> list[tuple[datetime, float]]:
    """(block middle, median of the block's values) for every block in (start, end] that has a
    point. Empty blocks are absent, never zero."""
    buckets: dict[int, list[float]] = {}
    last = expected_blocks(start, end, block) - 1
    for t, v in pts:
        if not start < t <= end:
            continue
        buckets.setdefault(min(int((t - start) / block), last), []).append(v)
    return [(start + block * (i + 0.5), statistics.median(v)) for i, v in sorted(buckets.items())]


def expected_blocks(start: datetime, end: datetime, block: timedelta) -> int:
    return max(1, math.ceil((end - start) / block))


def trailing_mean(
    rows: Sequence[StoredReading], window: timedelta, coverage: timedelta
) -> list[tuple[datetime, float]]:
    """(t, mean of rows in (t - window, t]) at each row, as hub/assess.py judges a mean window:
    a row is skipped until the rows before it span `coverage`."""
    pts = points(rows)
    out = []
    lo, total = 0, 0.0
    for i, (t, v) in enumerate(pts):
        total += v
        while pts[lo][0] <= t - window:
            total -= pts[lo][1]
            lo += 1
        if t - pts[lo][0] >= coverage:
            out.append((t, total / (i + 1 - lo)))
    return out


def hours_since(t: datetime, origin: datetime) -> float:
    return (t - origin) / HOUR


def series_out(points: Sequence[tuple[datetime, float]]) -> list[list]:
    return [[to_iso(t), v] for t, v in points]


# Nights (ring sleep_h): the window is (sleep_end - sleep_h, sleep_end]


@dataclass(frozen=True)
class Night:
    day: date  # local date of the sleep end
    start: datetime
    end: datetime
    sleep_h: float
    row: StoredReading


def nights(
    store: Store, crew: str | None, end: datetime, days: int, tz: ZoneInfo
) -> tuple[list[Night], bool]:
    """The crew's nights ending in (end - days, end], one per local day (the latest end wins),
    ascending, with the replay flag of the chosen rows."""
    rows, replay = choose(ok_rows(store, "sleep_h", end - DAY * days, end, crew))
    by_day: dict[date, Night] = {}
    for r in rows:
        t_end = parse_iso(r.measured_at)
        n = Night(t_end.astimezone(tz).date(), t_end - HOUR * r.val, t_end, r.val, r)
        cur = by_day.get(n.day)
        if cur is None or n.end > cur.end:
            by_day[n.day] = n
    return [by_day[d] for d in sorted(by_day)], replay


REST_BLOCK = timedelta(minutes=5)
REST_COVERAGE = 0.5


def night_rest_hr(
    store: Store, crew: str | None, night: Night, replay: bool
) -> tuple[float | None, list[StoredReading]]:
    """Median of the 5-minute HR block medians inside the night window, or None below 50 % of
    the window's blocks. Returns the HR rows used, for the inputs list."""
    rows = same_mode(ok_rows(store, "hr", night.start, night.end, crew), replay)
    blocks = block_medians(points(rows), night.start, night.end, REST_BLOCK)
    if len(blocks) < REST_COVERAGE * expected_blocks(night.start, night.end, REST_BLOCK):
        return None, rows
    return statistics.median(v for _, v in blocks), rows
