"""Derived indicators: cabin_ppco2 from cabin_co2 and cabin_p (spec 4.3)."""

from __future__ import annotations

from datetime import timedelta

from hub.contract import Reading
from hub.store import Store, StoredReading
from hub.timeutil import parse_iso

P_DEFAULT_HPA: float = 1013.25
MMHG_PER_HPA: float = 0.750062
P_WINDOW_S: int = 60


def ppco2_mmhg(co2_ppm: float, p_hpa: float) -> float:
    return co2_ppm * 1e-6 * p_hpa * MMHG_PER_HPA


def derive_ppco2(store: Store, co2: StoredReading) -> StoredReading | None:
    if co2.ind != "cabin_co2":
        return None
    t = parse_iso(co2.measured_at)
    window = timedelta(seconds=P_WINDOW_S)
    near = [
        p
        for p in store.readings_between(
            "cabin_p", t - window, t + window, include_start=True, include_end=True
        )
        if p.q == ("ok",)
    ]
    flags = [f for f in co2.q if f != "ok"]
    if near:
        p_hpa = near[-1].val
    else:
        p_hpa = P_DEFAULT_HPA
        flags.append("assumed_pressure")
    derived = Reading(
        v=1, node=co2.node, boot=co2.boot, seq=co2.seq, age_ms=co2.age_ms, ind="cabin_ppco2",
        val=ppco2_mmhg(co2.val, p_hpa), unit="mmHg", src=co2.src, dev=co2.dev,
        q=tuple(flags) or ("ok",), crew=co2.crew, code=None,
    )  # fmt: skip
    row, new = store.insert_reading(derived, parse_iso(co2.received_at), derived_from=co2.id)
    return row if new else None
