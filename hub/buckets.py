"""Readings for long chart windows: a few stored rows per time bucket, not the newest N.

The lanes show 24 hours or 7 days. At one reading every 5 s that is far more than the 5,000-row cap
of GET /api/readings, which keeps the newest rows, so a long window was cut to its last hours. With
bucket_s the route keeps, per bucket, the rows a chart needs to look the same and judge the same:
the first, last, lowest and highest assessable reading, the lowest and highest flagged one, and,
for an indicator judged on a 1-hour mean, the rows where that mean is lowest and highest. Every row
returned is a stored reading, unchanged; the 1-hour mean is added as `mean_1h`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hub.assess import _WINDOW_S, CREW_SCOPED, coverage_ok
from hub.store import Store

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def trailing_means(
    points: list[tuple[int, int, float, str | None]], *, scoped: bool, window: str = "mean_1h"
) -> dict[int, float | None]:
    """{id: mean} as hub/assess.py computes a mean window at each row: assessable rows in
    (t - window, t], crew-scoped like the assessor, None until the coverage rule is met.
    `points` are (id, epoch ms, val, crew) in ascending time order."""
    window_ms = _WINDOW_S[window] * 1000
    groups: dict[str | None, list[tuple[int, int, float, str | None]]] = {}
    for p in points:
        groups.setdefault(p[3] if scoped else None, []).append(p)
    out: dict[int, float | None] = {}
    for pts in groups.values():
        lo, total = 0, 0.0
        for i, (rid, ms, val, _) in enumerate(pts):
            total += val
            while pts[lo][1] <= ms - window_ms:
                total -= pts[lo][2]
                lo += 1
            covered = coverage_ok(window, (ms - pts[lo][1]) / 1000)
            out[rid] = total / (i + 1 - lo) if covered else None
    return out


def bucketed(
    store: Store,
    ind: str,
    *,
    bucket_s: int,
    limit: int,
    since: datetime | None = None,
    crew: str | None = None,
    mean_1h: bool = False,
) -> list[dict]:
    """The newest `limit` kept rows in ascending time order, as dicts."""
    bucket_ms = bucket_s * 1000
    picks = store.bucket_picks(ind, bucket_ms, since=since, crew=crew)
    means: dict[int, float | None] = {}
    if mean_1h:
        # The first rows of the window need the hour before it, as they had when assessed.
        after = since - timedelta(seconds=_WINDOW_S["mean_1h"]) if since else None
        points = store.ok_points(ind, after)
        means = trailing_means(points, scoped=ind in CREW_SCOPED)
        since_ms = (since - EPOCH) // timedelta(milliseconds=1) if since else None
        low: dict[int, tuple[float, int, int]] = {}
        high: dict[int, tuple[float, int, int]] = {}
        for rid, ms, _, row_crew in points:
            m = means[rid]
            if m is None or (since_ms is not None and ms < since_ms):
                continue
            if crew is not None and row_crew != crew:
                continue
            b = ms // bucket_ms
            if b not in low or m < low[b][0]:
                low[b] = (m, rid, ms)
            if b not in high or m > high[b][0]:
                high[b] = (m, rid, ms)
        for _, rid, ms in [*low.values(), *high.values()]:
            picks[rid] = ms
    ids = sorted(picks, key=lambda rid: (picks[rid], rid))[-limit:]
    rows = [r.to_dict() for r in store.readings_by_ids(ids)]
    if mean_1h:
        for r in rows:
            r["mean_1h"] = means.get(r["id"])
    return rows
