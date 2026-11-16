"""Camera sets (per crew): work per rep across sets, within the latest set, and the camera-tilt
agreement (D45 §6.5, §7). Work is mechanical work on the load, never food energy."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from hub.exercise import latest_reps
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal, spec_unit, trend_signal
from hub.signals.types import Input, Missing, Signal, Value
from hub.store import StoredRep
from hub.tilt import tilt_for_rep
from hub.timeutil import parse_iso, to_iso

REPLAY_NODES = frozenset({"sim-1"})
PRIOR_SETS = 14


@dataclass(frozen=True)
class SetRollup:
    session: str
    exercise: str | None
    started_at: datetime
    works: list[float]  # work_j / g per rep, in rep order (mass x ROM, so sets at any g compare)
    tilt_share: float | None  # share of reps with a tilt witness, of the reps that could have one
    tilt_offset_ms: float | None  # median |offset| of the witnessed reps
    replay: bool
    reps: list[StoredRep]

    @property
    def work(self) -> float:
        return statistics.median(self.works)


def _rollup(ctx: Ctx, row: tuple) -> SetRollup | None:
    cam = latest_reps([r for r in ctx.store.reps_for_session(row[0]) if r.src == "camera"])
    usable = [r for r in cam if r.g > 0 and r.work_j is not None]
    if not usable:
        return None
    witness = [tilt_for_rep(ctx.store, r) for r in usable]
    could = [w for w in witness if w is not None]
    seen = [w for w in could if w["seen"]]
    return SetRollup(
        session=row[0], exercise=row[6], started_at=parse_iso(row[4]),
        works=[r.work_j / r.g for r in usable],  # type: ignore[operator]
        tilt_share=len(seen) / len(could) if could else None,
        tilt_offset_ms=statistics.median(abs(w["offset_ms"]) for w in seen) if seen else None,
        replay=any(r.node in REPLAY_NODES for r in usable), reps=usable,
    )  # fmt: skip


def sets(ctx: Ctx, crew: str | None, spec: Spec) -> tuple[list[SetRollup], bool]:
    """The crew's camera sets started in the window, ascending, real sets only when any exist."""
    start = ctx.at - spec.window
    rows = [
        r for r in ctx.store.session_rows() if r[3] == crew and start < parse_iso(r[4]) <= ctx.at
    ]
    rolled = [s for s in (_rollup(ctx, r) for r in rows) if s is not None]
    rolled.sort(key=lambda s: s.started_at)
    real = [s for s in rolled if not s.replay]
    if real:
        return real, False
    return rolled, bool(rolled)


def _inputs(ss: list[SetRollup], at: datetime) -> list[Input]:
    reps = [r for s in ss for r in s.reps]
    if not reps:
        return []
    times = sorted(r.measured_at for r in reps)
    age = max(0.0, (at - parse_iso(times[-1])).total_seconds())
    return [Input("work_j", "camera", "camera", reps[0].node, len(reps), times[0], times[-1], age)]


def work_across_sets(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    if ss:
        ss = [s for s in ss if s.exercise == ss[-1].exercise]  # one exercise: the latest set's
    common = {
        "inputs": _inputs(ss, ctx.at), "replay": replay,
        "series": [[to_iso(s.started_at), s.work] for s in ss],
        "detail": {"exercise": ss[-1].exercise if ss else None},
    }  # fmt: skip
    pts = [((s.started_at - start).total_seconds() / 86400, s.work) for s in ss]
    return trend_signal(spec, ctx, crew, pts, max(len(pts), 1), start, "day",
                        "signals.missing.sets", **common)  # fmt: skip


def work_within_set(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    last = ss[-1] if ss else None
    works = last.works if last else []
    common = {
        "inputs": _inputs([last] if last else [], ctx.at), "replay": replay,
        "series": [[i + 1, w] for i, w in enumerate(works)],
        "detail": {"session": last.session if last else None,
                   "exercise": last.exercise if last else None},
    }  # fmt: skip
    pts = [(float(i + 1), w) for i, w in enumerate(works)]
    return trend_signal(spec, ctx, crew, pts, max(len(pts), 1), start, "rep",
                        "signals.missing.reps", **common)  # fmt: skip


def tilt_agreement(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    withv = [s for s in ss if s.tilt_offset_ms is not None]
    common = {
        "inputs": _inputs(withv, ctx.at), "replay": replay,
        "series": [[to_iso(s.started_at), s.tilt_offset_ms] for s in withv],
        "detail": {"tilt_share": withv[-1].tilt_share if withv else None},
    }  # fmt: skip
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, max(len(withv) - 1, 0), start, None,
                  alpha=None)  # fmt: skip
    if len(withv) < 2:
        return nodata(spec, crew, meth, [Missing("signals.missing.priorSets", spec.min_n,
                                                 max(len(withv) - 1, 0))], **common)  # fmt: skip

    def range_before(i: int) -> M.Baseline | None:
        prior = [s.tilt_offset_ms for s in withv[max(0, i - PRIOR_SETS) : i]]
        return M.own_baseline(prior, min_n=spec.min_n)  # type: ignore[arg-type]

    b = range_before(len(withv) - 1)
    if b is None:
        n_prior = min(len(withv) - 1, PRIOR_SETS)
        key = "signals.missing.priorSets" if n_prior < spec.min_n else "signals.missing.spread"
        return nodata(spec, crew, meth, [Missing(key, spec.min_n, n_prior)], **common)
    x = withv[-1].tilt_offset_ms
    assert x is not None
    value = Value(x, b.low, b.high, spec_unit(spec))
    headline = ("signals.baseline.above" if x > b.high else
                "signals.baseline.below" if x < b.low else "signals.baseline.inside")  # fmt: skip
    prev = range_before(len(withv) - 2)
    notable = (M.outside(x, b, spec.side) and prev is not None
               and M.outside(withv[-2].tilt_offset_ms, prev, spec.side))  # type: ignore[arg-type]  # fmt: skip
    return signal(spec, crew, "notable" if notable else "steady", headline, value, meth, **common)


def daily_work(ss: list[SetRollup], tz) -> dict:
    """{local day of the set start: sum of work_j / g over the day's sets}."""
    out: dict = {}
    for s in ss:
        d = s.started_at.astimezone(tz).date()
        out[d] = out.get(d, 0.0) + sum(s.works)
    return out
