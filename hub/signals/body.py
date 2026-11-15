"""Nightly body values (per crew): own-baseline ranges and 14-night trends (D45 §6.1, §6.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from hub.signals import inputs as I
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal, spec_unit, trend_signal
from hub.signals.types import Missing, Signal, Value
from hub.store import StoredReading

RECENT_NIGHT = timedelta(hours=36)
BASELINE_DAYS = 14
FETCH_DAYS = 31  # the latest night, the night before, and 14 prior nights for each


def nightly(
    ctx: Ctx, source: str, ind: str, crew: str | None, days: int
) -> tuple[dict[date, tuple[datetime, float]], list[StoredReading], bool]:
    """{local day of the night's end: (night end, value)}, the rows used, and the replay flag.
    `source` "night_rest_hr" gives the nightly resting HR; else `ind` is read per night."""
    nights, replay = I.nights(ctx.store, crew, ctx.at, days, ctx.tz)
    out: dict[date, tuple[datetime, float]] = {}
    used: list[StoredReading] = [n.row for n in nights]
    if source == "night_rest_hr":
        for n in nights:
            v, rows = I.night_rest_hr(ctx.store, crew, n, replay)
            used += rows
            if v is not None:
                out[n.day] = (n.end, v)
    elif ind == "sleep_h":
        out = {n.day: (n.end, n.sleep_h) for n in nights}
    else:  # a nightly reading timed at the night's end (spo2), matched to that night
        rows = I.same_mode(
            I.ring_rows(I.ok_rows(ctx.store, ind, ctx.at - I.DAY * days, ctx.at, crew)), replay
        )
        night_days = {n.day for n in nights}
        for t, v in I.points(rows):
            d = t.astimezone(ctx.tz).date()
            if d in night_days:
                out[d] = (t, v)
        used += rows
    return out, used, replay


def baseline(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    values, used, replay = nightly(ctx, spec.source, spec.ind or "", crew, FETCH_DAYS)
    start = ctx.at - spec.window
    pts = sorted(values.values())
    common = {"inputs": I.describe(used, ctx.at), "replay": replay, "series": I.series_out(pts)}
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, 0, start, None, alpha=None)
    if not values or ctx.at - max(values.values())[0] > RECENT_NIGHT:
        return nodata(spec, crew, meth, [Missing("signals.missing.recentNight")], **common)
    today = max(values)

    def range_for(day: date) -> tuple[M.Baseline | None, int]:
        prior = [
            v for d, (_, v) in values.items() if day - timedelta(days=BASELINE_DAYS) <= d < day
        ]
        return M.own_baseline(prior, min_n=spec.min_n), len(prior)

    b, n_prior = range_for(today)
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, n_prior, start, None, alpha=None)
    if b is None:
        key = "signals.missing.priorDays" if n_prior < spec.min_n else "signals.missing.spread"
        return nodata(spec, crew, meth, [Missing(key, spec.min_n, n_prior)], **common)
    x = values[today][1]
    value = Value(x, b.low, b.high, spec_unit(spec))
    if x > b.high:
        headline = "signals.baseline.above"
    elif x < b.low:
        headline = "signals.baseline.below"
    else:
        headline = "signals.baseline.inside"
    # Notable only when the night before was outside its own range on the same side, too.
    yesterday = today - timedelta(days=1)
    notable = False
    if M.outside(x, b, spec.side) and yesterday in values:
        yb, _ = range_for(yesterday)
        notable = yb is not None and M.outside(values[yesterday][1], yb, spec.side)
    return signal(spec, crew, "notable" if notable else "steady", headline, value, meth, **common)


def night_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    values, used, replay = nightly(ctx, spec.source, spec.ind or "", crew, spec.window.days)
    # A 14 x 24 h window touches 15 local dates; keep the last 14 so "14 nights" means 14.
    today = ctx.at.astimezone(ctx.tz).date()
    values = {d: v for d, v in values.items() if (today - d).days < spec.window.days}
    start = ctx.at - spec.window
    ends = sorted(values.values())
    common = {"inputs": I.describe(used, ctx.at), "replay": replay, "series": I.series_out(ends)}
    pts = [((t - start) / I.DAY, v) for t, v in ends]
    return trend_signal(spec, ctx, crew, pts, spec.window.days, start, "day",
                        "signals.missing.nights", **common)  # fmt: skip
