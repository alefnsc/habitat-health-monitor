"""Lagged cross-references (D45 §6.4): side by side, never notable, never a cause.

Both sides of a pair come from the same mode: the second side follows the first side's real or
replay choice, so a replay value is never paired with a real one.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from hub.contract import INTAKE_ORDER
from hub.signals import inputs as I
from hub.signals import lift
from hub.signals import methods as M
from hub.signals.body import nightly
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal
from hub.signals.daily import by_day
from hub.signals.types import Missing, Signal, Value

DAY = timedelta(days=1)
CABIN_LAGS_H = (0, 1, 2, 3)


def _pair_signal(ctx: Ctx, spec: Spec, crew: str | None, xs: dict, ys: dict, lag: timedelta,
                 **common) -> Signal:  # fmt: skip
    start = ctx.at - spec.window
    pairs = M.lagged_pairs(xs, ys, lag=lag)
    meth = method(spec, ctx, "spearman_fisher_z", M.SPEARMAN_REF, len(pairs), start, None)
    table = [[str(k), x, y] for k, x, y in pairs]
    if not pairs:
        return nodata(spec, crew, meth, [Missing("signals.missing.pairs", spec.min_n, 0)],
                      **common)  # fmt: skip
    sp = M.spearman([(x, y) for _, x, y in pairs], min_n=spec.min_n)
    if sp is None:
        return signal(spec, crew, "steady", "signals.pair.few", None, meth, pairs=table, **common)
    value = Value(sp.rho, sp.low, sp.high, "rho")
    return signal(spec, crew, "steady", "signals.pair.rho", value, meth, pairs=table, **common)


def _sleep(ctx: Ctx, spec: Spec, crew: str | None):
    """{day d: sleep_h of the night that ends on day d + 1}, keyed by the night's end day."""
    vals, used, replay = nightly(ctx, "night_value", "sleep_h", crew, spec.window.days)
    return {d: v for d, (_, v) in vals.items()}, used, replay


def training_vs_rest_hr(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    vals, used, replay = nightly(ctx, "night_rest_hr", "hr", crew, spec.window.days)
    ys = {d: v for d, (_, v) in vals.items()}
    ss, _ = lift.sets(ctx, crew, spec)
    ss = [s for s in ss if s.replay == replay]
    xs = lift.daily_work(ss, ctx.tz)
    common = {"inputs": I.describe(used, ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def last_meal_vs_sleep(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    ys, used, replay = _sleep(ctx, spec, crew)
    start = ctx.at - spec.window
    rows = [r for ind in INTAKE_ORDER for r in I.ok_rows(ctx.store, ind, start, ctx.at, crew)]
    rows = I.same_mode(rows, replay)
    last = by_day(rows, ctx.tz, "last")
    # x is the local clock time of the day's last logged meal, in hours (19.5 = 19:30)
    xs = {}
    for d, (t, _) in last.items():
        lt = t.astimezone(ctx.tz)
        xs[d] = lt.hour + lt.minute / 60
    common = {"inputs": I.describe([*used, *rows], ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def space_weather_vs_sleep(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    ys, used, replay = _sleep(ctx, spec, crew)
    start = ctx.at - spec.window
    rows = I.same_mode(I.ok_rows(ctx.store, "space_weather", start, ctx.at, None), replay)
    xs = {d: v for d, (_, v) in by_day(rows, ctx.tz, "max").items()}
    common = {"inputs": I.describe([*used, *rows], ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def _hourly(pts: list[tuple[datetime, float]]) -> dict[datetime, float]:
    groups: dict[datetime, list[float]] = {}
    for t, v in pts:
        groups.setdefault(t.replace(minute=0, second=0, microsecond=0), []).append(v)
    return {h: statistics.median(v) for h, v in groups.items()}


def cabin_vs_earth(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    """Hourly medians side by side at lags 0-3 h. No lag is picked as the best one."""
    start = ctx.at - spec.window
    cabin, replay = I.choose(I.ok_rows(ctx.store, "cabin_temp", start, ctx.at, None))
    earth = I.same_mode(I.ok_rows(ctx.store, "earth_temp", start, ctx.at, None), replay)
    xs, ys = _hourly(I.points(earth)), _hourly(I.points(cabin))
    meth = method(spec, ctx, "spearman_fisher_z", M.SPEARMAN_REF, 0, start, None)
    common = {"inputs": I.describe([*cabin, *earth], ctx.at), "replay": replay}
    lags, table = [], []
    for h in CABIN_LAGS_H:
        pairs = M.lagged_pairs(xs, ys, lag=timedelta(hours=h))  # earth at t, cabin at t + h
        sp = M.spearman([(x, y) for _, x, y in pairs], min_n=spec.min_n)
        lags.append({"lag_h": h, "n": len(pairs), "rho": sp.rho if sp else None,
                     "low": sp.low if sp else None, "high": sp.high if sp else None})  # fmt: skip
        table += [[I.to_iso(k), x, y, h] for k, x, y in pairs]
    if not table:
        return nodata(spec, crew, meth, [Missing("signals.missing.pairs", spec.min_n, 0)],
                      detail={"lags": lags}, **common)  # fmt: skip
    head = "signals.pair.rho" if any(x["rho"] is not None for x in lags) else "signals.pair.few"
    return signal(spec, crew, "steady", head, None, meth, pairs=table, detail={"lags": lags},
                  **common)  # fmt: skip
