"""Shared pieces of the signal builders: the evaluation context and the Signal constructors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from hub.contract import DERIVED, INDICATORS
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.types import Method, Missing, Signal, Value
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import to_iso

TREND_REF = M.MK_REF + "; " + M.SEN_REF


@dataclass(frozen=True)
class Ctx:
    store: Store
    rules: dict[str, Rule]
    at: datetime
    tz: ZoneInfo


def unit_of(ind: str | None) -> str:
    return INDICATORS.get(ind or "") or DERIVED.get(ind or "", "")


def spec_unit(spec: Spec) -> str:
    return spec.unit or unit_of(spec.ind)


def need_for(spec: Spec, expected: int) -> int:
    """Points needed: at least min_n, and at least `coverage` of the expected points."""
    return max(spec.min_n, math.ceil(spec.coverage * expected))


def method(
    spec: Spec, ctx: Ctx, name: str, ref: str, n: int, start: datetime,
    coverage: float | None, alpha: float | None = M.ALPHA,
) -> Method:  # fmt: skip
    return Method(name, ref, alpha, n, spec.min_n, to_iso(start), to_iso(ctx.at), coverage)


def signal(
    spec: Spec, crew: str | None, state: str, headline: str, value: Value | None, meth: Method,
    **kw,
) -> Signal:  # fmt: skip
    return Signal(
        spec.id, spec.kind, crew, state, headline, value, meth,  # type: ignore[arg-type]
        limits=list(spec.limits), can_trigger=spec.can_trigger, **kw,
    )  # fmt: skip


def nodata(spec: Spec, crew: str | None, meth: Method, missing: list[Missing], **kw) -> Signal:
    return signal(spec, crew, "not_enough_data", "signals.nodata", None, meth, missing=missing,
                  **kw)  # fmt: skip


def trend_headline(t: M.Trend) -> str:
    if not t.notable:
        return "signals.trend.flat"
    return "signals.trend.up" if t.slope > 0 else "signals.trend.down"


def trend_signal(
    spec: Spec, ctx: Ctx, crew: str | None, pts: list[tuple[float, float]], expected: int,
    start: datetime, per: str, missing_key: str, **common,
) -> Signal:  # fmt: skip
    """The shared trend path: `pts` are (t in `per` units since start, value)."""
    need = need_for(spec, expected)
    meth = method(spec, ctx, "mann_kendall_sen", TREND_REF, len(pts), start, len(pts) / expected)
    if len(pts) < need:
        return nodata(spec, crew, meth, [Missing(missing_key, need, len(pts))], **common)
    t = M.trend(pts, min_n=spec.min_n)
    if t is None:
        return nodata(spec, crew, meth, [Missing(missing_key, need, len(pts))], **common)
    value = Value(t.slope, t.low, t.high, spec_unit(spec), per)
    return signal(spec, crew, "notable" if t.notable else "steady", trend_headline(t), value,
                  meth, **common)  # fmt: skip
