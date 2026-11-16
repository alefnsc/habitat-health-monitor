"""Cabin, ISS and Earth series (crew None): 6-hour trends and the time-to-limit (D45 §6.1, §6.3)."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from hub.signals import inputs as I
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, need_for, nodata, signal, trend_signal
from hub.signals.types import Missing, Signal, Value
from hub.store import StoredReading

TTL_NOTABLE_H = 3.0
MEAN_1H_COVERAGE = timedelta(seconds=2700)  # as hub/assess.py: 45 minutes of a 1-hour window


def blocked(ctx: Ctx, spec: Spec) -> tuple[list[StoredReading], bool, list[tuple[datetime, float]]]:
    """(rows used, replay flag, block medians) of the spec's series over its window."""
    start = ctx.at - spec.window
    assert spec.ind is not None and spec.block is not None
    if spec.source == "cabin_mean_1h":
        # co2_1h judges a 1-hour mean: fit the trailing mean, built from an hour before the window.
        rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start - I.HOUR, ctx.at, None))
        pts = I.trailing_mean(rows, I.HOUR, MEAN_1H_COVERAGE)
    else:
        rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start, ctx.at, None))
        pts = I.points(rows)
    return rows, replay, I.block_medians(pts, start, ctx.at, spec.block)


def cabin_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    rows, replay, blocks = blocked(ctx, spec)
    common = {"inputs": I.describe(rows, ctx.at), "replay": replay, "series": I.series_out(blocks)}
    pts = [(I.hours_since(t, start), v) for t, v in blocks]
    expected = I.expected_blocks(start, ctx.at, spec.block)
    return trend_signal(spec, ctx, crew, pts, expected, start, "h", "signals.missing.blocks",
                        **common)  # fmt: skip


def time_to_limit(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    rows, replay, blocks = blocked(ctx, spec)
    expected = I.expected_blocks(start, ctx.at, spec.block)
    meth = method(spec, ctx, "sen_time_to_limit", M.TTL_REF, len(blocks), start,
                  len(blocks) / expected)  # fmt: skip
    common = {"inputs": I.describe(rows, ctx.at), "replay": replay, "series": I.series_out(blocks)}
    rule = ctx.rules.get(spec.rule_id or "")
    if rule is None or rule.ok is None:
        return nodata(spec, crew, meth, [Missing("signals.missing.rule")], **common)
    need = need_for(spec, expected)
    if len(blocks) < need:
        return nodata(spec, crew, meth, [Missing("signals.missing.blocks", need, len(blocks))],
                      **common)  # fmt: skip
    pts = [(I.hours_since(t, start), v) for t, v in blocks]
    mk = M.mann_kendall([v for _, v in pts])
    sen = M.sen_slope(pts, mk.var_s) if mk else None
    if sen is None:
        return nodata(spec, crew, meth, [Missing("signals.missing.blocks", need, len(blocks))],
                      **common)  # fmt: skip
    current = statistics.median(v for _, v in blocks[-3:])
    reference: dict = {"rule_id": rule.id, "source_kind": rule.source_kind, "limit": None}
    if not rule.ok.contains(current):
        # Already outside: the assessor's band status says so; no time is shown.
        return signal(spec, crew, "steady", "signals.ttl.outside", None, meth, reference=reference,
                      **common)  # fmt: skip
    limit = rule.ok.max if sen.slope > 0 else rule.ok.min
    if limit is None:
        return signal(spec, crew, "steady", "signals.ttl.away", None, meth, reference=reference,
                      **common)  # fmt: skip
    reference["limit"] = limit
    hours = M.time_to_limit(current, sen.low, sen.high, limit)
    if hours is None:
        return signal(spec, crew, "steady", "signals.ttl.none", None, meth, reference=reference,
                      **common)  # fmt: skip
    mid = (limit - current) / sen.slope if sen.slope else hours[1]
    value = Value(min(max(mid, hours[0]), hours[1]), hours[0], hours[1], "h")
    state = "notable" if hours[0] < TTL_NOTABLE_H else "steady"
    return signal(spec, crew, state, "signals.ttl.reaches", value, meth, reference=reference,
                  **common)  # fmt: skip
