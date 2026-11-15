"""Daily body and food values (per crew): body mass and water-logged trends (D45 §6.5, §7)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from hub.signals import inputs as I
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, trend_signal
from hub.signals.types import Signal
from hub.store import StoredReading

How = Literal["sum", "last", "max"]


def by_day(
    rows: Iterable[StoredReading], tz: ZoneInfo, how: How
) -> dict[date, tuple[datetime, float]]:
    """{local day: (time of the day's last row, value)}. A day without a row is absent, never 0."""
    out: dict[date, tuple[datetime, float]] = {}
    for t, v in I.points(rows):
        d = t.astimezone(tz).date()
        prev = out.get(d)
        if prev is None:
            out[d] = (t, v)
        elif how == "sum":
            out[d] = (max(prev[0], t), prev[1] + v)
        elif how == "max":
            out[d] = (max(prev[0], t), max(prev[1], v))
        elif t >= prev[0]:
            out[d] = (t, v)
    return out


def daily_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    assert spec.ind is not None
    start = ctx.at - spec.window
    rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start, ctx.at, crew))
    days = by_day(rows, ctx.tz, "sum" if spec.source == "daily_sum" else "last")
    first = start.astimezone(ctx.tz).date()
    pts = [(float((d - first).days), v) for d, (_, v) in sorted(days.items())]
    common = {
        "inputs": I.describe(rows, ctx.at), "replay": replay,
        "series": I.series_out([tv for _, tv in sorted(days.items())]),
    }  # fmt: skip
    return trend_signal(spec, ctx, crew, pts, spec.window.days, start, "day",
                        "signals.missing.days", **common)  # fmt: skip
