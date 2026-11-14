"""S4: band boundary tests for data/thresholds.json, through the real API.

Written against docs/drafts/s2-nasa-thresholds.md and s3-clinical-bands.md. Skipped until
H4b commits data/thresholds.json; from then on they run and must pass.

Method: every case runs in a fresh app and database (the `settings` fixture gives each test
its own tmp_path), with the clock fixed so the assessed reading is at T = 2026-11-14T15:00Z
(12:00 hub-local), so `lux_general` hours apply. One contract-valid reading is POSTed and the
single entry for that indicator is read from GET /api/status.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.contract import INDICATORS
from hub.tests.helpers import msg

THRESHOLDS = Path(__file__).resolve().parents[2] / "data" / "thresholds.json"
T = datetime(2026, 11, 14, 15, 0, 0, tzinfo=UTC)
MMHG_PER_PPM = 0.000750062

pytestmark = pytest.mark.skipif(
    not THRESHOLDS.exists(), reason="S4: waiting for H4b to commit data/thresholds.json"
)

BODY = {"hr", "spo2", "body_temp", "bp_sys", "bp_dia", "glucose", "sleep_h", "mood"}
CABIN_DEV = {"cabin_temp": "BME280", "cabin_rh": "BME280", "cabin_p": "BME280",
             "cabin_co2": "SCD41", "cabin_lux": "BH1750"}  # fmt: skip


class Rig:
    def __init__(self, client: TestClient, clock) -> None:
        self.c, self.clock, self.n = client, clock, 0

    def body(self, ind: str, val: float, **kw) -> dict:
        self.n += 1
        return msg(
            node="manual", boot=1, seq=self.n, ind=ind, val=val, unit=INDICATORS[ind],
            src="self", dev="manual", crew="crew-a", **kw,
        )  # fmt: skip

    def cabin(self, ind: str, val: float, **kw) -> dict:
        self.n += 1
        return msg(
            node="cabin-1", boot=1, seq=self.n, ind=ind, val=val, unit=INDICATORS[ind],
            src="hobby", dev=CABIN_DEV[ind], **kw,
        )  # fmt: skip

    def post(self, ind: str, val: float, at: datetime = T, **kw) -> None:
        self.clock.set(at)
        m = self.body(ind, val, **kw) if ind in BODY else self.cabin(ind, val, **kw)
        r = self.c.post("/api/readings", json=m)
        assert r.status_code == 201, r.text

    def entry(self, ind: str) -> dict:
        r = self.c.get("/api/status")
        assert r.status_code == 200
        return next(e for e in r.json()["results"] if e["ind"] == ind)

    def internal(self, ind: str, val: float, dev: str) -> None:
        from hub.contract import parse_reading

        self.clock.set(T)
        self.n += 1
        r = parse_reading(msg(node="nasa", boot=0, seq=self.n, ind=ind, val=val,
                              unit=INDICATORS[ind], src="nasa", dev=dev, q=["ok"]))  # fmt: skip
        res = self.c.app.state.ingestor.ingest_internal(r)
        assert res.reason is None, res.reason


@pytest.fixture
def rig(settings, clock):
    s = replace(settings, thresholds_path=THRESHOLDS)
    clock.set(T)
    with TestClient(create_app(s, clock=clock)) as c:
        yield Rig(c, clock)


def _single(ind, cases):
    return pytest.mark.parametrize("val,expected", cases, ids=[f"{v}-{e}" for v, e in cases])


def _check(rig, ind, val, expected):
    rig.post(ind, val)
    assert rig.entry(ind)["status"] == expected


@_single("hr", [(40, "act"), (41, "watch"), (50, "watch"), (51, "ok"), (90, "ok"),
                (91, "watch"), (130, "watch"), (131, "act")])  # fmt: skip
def test_boundaries_hr(rig, val, expected):
    _check(rig, "hr", val, expected)


@_single("spo2", [(91, "act"), (92, "watch"), (95, "watch"), (96, "ok"), (100, "ok")])
def test_boundaries_spo2(rig, val, expected):
    _check(rig, "spo2", val, expected)


@_single("body_temp", [(35.0, "act"), (35.1, "watch"), (36.0, "watch"), (36.1, "ok"),
                       (38.0, "ok"), (38.1, "watch"), (39.5, "watch")])  # fmt: skip
def test_boundaries_body_temp(rig, val, expected):
    _check(rig, "body_temp", val, expected)


@_single("bp_sys", [(90, "act"), (91, "watch"), (110, "watch"), (111, "ok"), (129, "ok"),
                    (130, "watch"), (180, "watch"), (181, "act")])  # fmt: skip
def test_boundaries_bp_sys(rig, val, expected):
    _check(rig, "bp_sys", val, expected)


@_single("bp_dia", [(79, "ok"), (80, "watch"), (120, "watch"), (121, "act")])
def test_boundaries_bp_dia(rig, val, expected):
    _check(rig, "bp_dia", val, expected)


@_single("glucose", [(53, "act"), (54, "watch"), (69, "watch"), (70, "ok"), (139, "ok"),
                     (140, "watch"), (199, "watch"), (200, "act")])  # fmt: skip
def test_boundaries_glucose(rig, val, expected):
    # glucose_high 140-199 is S3 decision 1: update with the approved table.
    _check(rig, "glucose", val, expected)


@_single("sleep_h", [(6.9, "watch"), (7.0, "ok"), (10.0, "ok")])
def test_boundaries_sleep(rig, val, expected):
    _check(rig, "sleep_h", val, expected)


@_single("mood", [(2, "watch"), (3, "ok")])
def test_boundaries_mood(rig, val, expected):
    rig.post("mood", val)
    e = rig.entry("mood")
    assert e["status"] == expected
    if expected == "watch":
        assert e["rule_id"] == "mood_self" and e["source_kind"] == "team_convention"


MOOD_CASES = {
    "a_daily_mean_2.2857": ([2, 2, 3, 2, 2, 2, 3], 24, "watch", "mood_7d"),
    "b_daily_all_3": ([3] * 7, 24, "ok", None),
    "c_12h_mean_2.5": ([2, 3, 2, 3, 2, 3, 2, 3], 12, "ok", None),
    "d_12h_mean_2.375": ([2, 3, 2, 3, 2, 2, 2, 3], 12, "watch", "mood_7d"),
    "e_last_is_2": ([2, 2, 3, 2, 2, 3, 2], 24, "watch", None),
}


@pytest.mark.parametrize("vals,step_h,status,rule_id", MOOD_CASES.values(), ids=MOOD_CASES.keys())
def test_boundaries_mood_7d(rig, vals, step_h, status, rule_id):
    n = len(vals)
    for i, v in enumerate(vals):
        rig.post("mood", v, at=T - timedelta(hours=step_h * (n - 1 - i)))
    e = rig.entry("mood")
    assert e["status"] == status
    if rule_id:  # in cases a-d the last reading is 3, so mood_7d decides the entry
        assert e["rule_id"] == rule_id


@_single("cabin_temp", [(17.9, "act"), (18.0, "watch"), (22.0, "ok"), (25.0, "ok"),
                        (25.1, "watch"), (27.0, "watch"), (27.1, "act")])  # fmt: skip
def test_boundaries_cabin_temp(rig, val, expected):
    # Bounding box of Figure 6.2-2 (S2 decision 1). Update if the operator chooses the polygon.
    _check(rig, "cabin_temp", val, expected)


@_single("cabin_rh", [(24, "act"), (25, "watch"), (30, "ok"), (60, "ok"), (61, "watch"),
                      (75, "watch"), (76, "act")])  # fmt: skip
def test_boundaries_cabin_rh(rig, val, expected):
    _check(rig, "cabin_rh", val, expected)


@_single("cabin_lux", [(349, "watch"), (350, "ok")])
def test_boundaries_lux(rig, val, expected):
    _check(rig, "cabin_lux", val, expected)


def _co2_pairs(rig, ppm, times):
    for t in times:
        rig.post("cabin_p", 1000.0, at=t)
        rig.post("cabin_co2", ppm, at=t)


CO2_1H = [(3999, "ok"), (4000, "act")]
CO2_7D = [(3333, "ok"), (3334, "watch")]


@pytest.mark.parametrize("ppm,status", CO2_1H, ids=[f"1h-{p}-{s}" for p, s in CO2_1H])
def test_boundaries_co2_1h(rig, ppm, status):
    _co2_pairs(rig, ppm, [T - timedelta(minutes=5 * k) for k in range(10, -1, -1)])  # 11 pairs
    e = rig.entry("cabin_ppco2")
    assert e["status"] == status and e["rule_id"] == "co2_1h"
    assert e["val"] == pytest.approx(ppm * MMHG_PER_PPM, rel=1e-3)  # 2.9995 / 3.00025 mmHg


@pytest.mark.parametrize("ppm,status", CO2_7D, ids=[f"7d-{p}-{s}" for p, s in CO2_7D])
def test_boundaries_co2_7d(rig, ppm, status):
    _co2_pairs(rig, ppm, [T - timedelta(hours=k) for k in range(25, -1, -1)])  # 26 pairs, 25 h
    e = rig.entry("cabin_ppco2")
    assert e["status"] == status and e["rule_id"] == "co2_7d"


@_single("rad_dose_cum", [(299.9, "ok"), (300, "watch"), (539.9, "watch"), (540, "act")])
def test_radiation_career(rig, val, expected):
    rig.internal("rad_dose_cum", val, "OSDR")
    assert rig.entry("rad_dose_cum")["status"] == expected


@_single("space_weather", [(0, "ok"), (1, "watch"), (2, "act")])
def test_radiation_spe(rig, val, expected):
    rig.internal("space_weather", val, "DONKI")
    e = rig.entry("space_weather")
    assert e["status"] == expected
    if expected != "ok":
        assert e["rule_id"] == "radiation_spe"


def test_flagged_reading_unknown(rig):
    rig.post("hr", 120, q=["motion"])
    e = rig.entry("hr")
    assert e["status"] == "unknown" and e["rule_id"] is None and e["q"] == ["motion"]


def test_result_carries_source(rig):
    rig.post("hr", 95)
    e = rig.entry("hr")
    assert e["rule_id"] == "hr_rest_high" and e["status"] == "watch"
    assert e["source_kind"] == "clinical_ref"
    assert "NEWS2" in e["source_ref"]
    assert e["guidance_id"] == "hr_rest_high.watch"
    assert e["src"] and e["dev"] and e["reading_id"]
