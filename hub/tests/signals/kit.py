"""Builders shared by the signals tests: a rig with the real thresholds and one-line inputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from hub.contract import INDICATORS
from hub.signals.engine import evaluate
from hub.signals.types import Signal
from hub.tests.helpers import Rig, T

TZ = "America/Sao_Paulo"
REAL_RULES = Path(__file__).resolve().parents[3] / "data" / "thresholds.json"
END = T.replace(hour=10)  # 07:00 local


def real_rig(tmp_path, clock) -> Rig:
    return Rig(tmp_path, clock, rule_files=(REAL_RULES,))


def one(
    rig: Rig, sid: str, crew: str | None = "crew-a", at: datetime = END + timedelta(hours=1)
) -> Signal:
    [s] = evaluate(rig.store, rig.assessor.rules, crews=[crew] if crew else [], at=at, tz=TZ,
                   ids=[sid])  # fmt: skip
    return s


def put_ref(
    rig: Rig, ind: str, val: float, at: datetime, *, node: str, dev: str, src: str,
    crew: str | None = None,
) -> None:  # fmt: skip
    """A reading Rig.put cannot build (no default device for the indicator)."""
    rig.clock.set(at)
    rig.seq += 1
    m = {"v": 1, "node": node, "boot": 1, "seq": rig.seq, "age_ms": 0, "ind": ind, "val": val,
         "unit": INDICATORS[ind], "src": src, "dev": dev, "q": ["ok"]}  # fmt: skip
    if crew is not None:
        m["crew"] = crew
    res = rig.ing.ingest_reading(m, channel="test")
    assert res.reason is None, res.reason


def meal(rig: Rig, at: datetime, water: float, crew: str = "crew-a") -> None:
    rig.put("intake_water_ml", water, at, node="food", dev="catalog", src="self", crew=crew)


def night(rig: Rig, end: datetime, sleep_h: float, crew: str = "crew-a") -> None:
    rig.put("sleep_h", sleep_h, end, node="ring-1", dev="RING", crew=crew)


def lift_set(rig: Rig, sid: str, start: datetime, works: list[float], crew: str = "crew-a",
             exercise: str = "curl", node: str = "camera", g: float = 9.81,
             turn_ms: int | None = None) -> None:  # fmt: skip
    """One camera set: a session row and one camera rep per work value (joules at `g`).
    Rep i ends at start + 5 i s and lasts 1.5 s; `turn_ms` puts its turnaround that far in."""
    rig.store.insert_session(sid, 5.0, g, crew, start, exercise)
    for i, w in enumerate(works, 1):
        rig.clock.set(start + timedelta(seconds=5 * i))
        rep = {
            "v": 1, "node": node, "boot": 1, "seq": rig.seq + i, "age_ms": 0, "type": "rep",
            "session": sid, "rep": i, "src": "camera", "peak_n": 60.0, "work_j": w,
            "rom_m": 0.4, "g": g, "mass_kg": 5.0, "t0_ms": 0, "t1_ms": 1500,
            "exercise": exercise,
        }  # fmt: skip
        if turn_ms is not None:
            rep["t_turn_ms"] = turn_ms
        assert rig.ing.ingest_rep(rep, channel="test").reason is None
    rig.seq += len(works)


def ring_hr(rig: Rig, end: datetime, sleep_h: float, hr: float, crew: str = "crew-a") -> None:
    """A ring night ending at `end` with one ring HR sample in every 5-minute block of it."""
    for k in range(int(sleep_h * 12), 0, -1):
        rig.put("hr", hr, end - timedelta(minutes=5 * k - 2), node="ring-1", dev="RING", crew=crew)
    night(rig, end, sleep_h, crew)
