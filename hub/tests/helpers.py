"""Builders shared by hub tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hub.assess import Assessor
from hub.contract import DERIVED, INDICATORS, Reading, parse_reading
from hub.derive import derive_ppco2
from hub.ingest import Ingestor
from hub.store import Store
from hub.thresholds import load_rule_files


def msg(**kw) -> dict:
    base = {
        "v": 1, "node": "cabin-1", "boot": 2, "seq": 10, "age_ms": 0, "ind": "cabin_co2",
        "val": 812, "unit": "ppm", "src": "hobby", "dev": "SCD41", "q": ["ok"],
    }  # fmt: skip
    base.update(kw)
    return base


def reading(**kw) -> Reading:
    return parse_reading(msg(**kw))


def hr(seq: int = 1, val: float = 72, **kw) -> dict:
    return msg(node="vitals-1", boot=3, seq=seq, ind="hr", val=val, unit="bpm",
               src="hobby", dev="MAX30102", **kw)  # fmt: skip


FIXTURES = Path(__file__).parent / "fixtures"
MAIN_RULES = FIXTURES / "thresholds_test.json"
FOOD_RULES = FIXTURES / "thresholds_food_test.json"
T = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
T_F = datetime(2026, 11, 14, 15, 0, 0, tzinfo=UTC)

_DEV = {
    "cabin_temp": "BME280", "cabin_rh": "BME280", "cabin_p": "BME280", "cabin_co2": "SCD41",
    "cabin_lux": "BH1750", "hr": "MAX30102", "sleep_h": "manual", "motion": "MPU6050",
    "load_raw": "HX711",
}  # fmt: skip


class Rig:
    """Store + Assessor + Ingestor with a settable clock and an emit spy."""

    def __init__(self, tmp_path, clock, rule_files=(MAIN_RULES,), escalation=None):
        self.clock = clock
        self.store = Store(tmp_path / "rig.db")
        self.events: list[tuple[str, dict]] = []
        self.assessor = Assessor(
            self.store,
            load_rule_files(list(rule_files)),
            tz="America/Sao_Paulo",
            escalation=escalation,
            emit=self.emit,
        )
        self.ing = Ingestor(
            self.store, clock, emit=self.emit, deriver=derive_ppco2, assessor=self.assessor
        )
        self.seq = 0
        self.alert_cb: list = []
        self.assessor.on_alert(self.alert_cb.append) if hasattr(self.assessor, "on_alert") else None

    def emit(self, kind, data):
        self.events.append((kind, data))

    def put(self, ind, val, at=T, *, node=None, **kw):
        """Ingest one reading received at `at`; returns the IngestResult."""
        self.clock.set(at)
        self.seq += 1
        unit = INDICATORS.get(ind) or DERIVED[ind]
        is_food = ind.startswith("intake_")
        m = {
            "v": 1, "node": node or ("food" if is_food else "cabin-1"), "boot": 1,
            "seq": self.seq, "age_ms": 0, "ind": ind, "val": val, "unit": unit,
            "src": "self" if is_food else "hobby", "dev": "catalog" if is_food else _DEV[ind],
            "q": ["ok"],
        }  # fmt: skip
        if ind == "hr":
            m["node"] = node or "vitals-1"
        if is_food:
            m["crew"] = "crew-a"
        m.update(kw)
        res = self.ing.ingest_reading(m, channel="test")
        assert res.reason is None, res.reason
        return res


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)


def hours(n: float) -> timedelta:
    return timedelta(hours=n)
