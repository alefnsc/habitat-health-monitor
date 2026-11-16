"""Daily body and food values (per crew): body mass and water-logged trends (D45 §6.5, §7)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from hub.signals import inputs as I
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, trend_signal
from hub.signals.types import Signal
from hub.store import StoredReading
from hub.timeutil import parse_iso

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


WEEKLY = frozenset({"body_mass_30d"})  # spec section 7: the slope is in kg per week


def daily_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    """One value per local day over the last `window.days` local dates. A (at - n d, at] window
    touches n + 1 local dates with the first one cut, so the dates are counted, not the hours.
    A day's sum (spec section 6.5) is a full 24 h total: the n complete days before today, as
    today is still open. A day's last value takes today too."""
    assert spec.ind is not None
    n = spec.window.days
    today = ctx.at.astimezone(ctx.tz).date()
    daily_sum = spec.source == "daily_sum"
    last = today - timedelta(days=1) if daily_sum else today
    first = last - timedelta(days=n - 1)
    start = datetime.combine(first, time(0), tzinfo=ctx.tz)
    # ok_rows is (start, end]: fetch from a day earlier, then keep the dates themselves
    fetched = I.ok_rows(ctx.store, spec.ind, start - timedelta(days=1), ctx.at, crew)
    inside = [r for r in fetched if first <= parse_iso(r.measured_at).astimezone(ctx.tz).date()
              <= last]  # fmt: skip
    rows, replay = I.choose(inside)
    days = by_day(rows, ctx.tz, "sum" if daily_sum else "last")
    per = "week" if spec.id in WEEKLY else "day"
    scale = 7.0 if per == "week" else 1.0
    pts = [((d - first).days / scale, v) for d, (_, v) in sorted(days.items())]
    common = {
        "inputs": I.describe(rows, ctx.at), "replay": replay,
        "series": I.series_out([tv for _, tv in sorted(days.items())]),
    }  # fmt: skip
    return trend_signal(spec, ctx, crew, pts, n, start, per, "signals.missing.days",
                        **common)  # fmt: skip
