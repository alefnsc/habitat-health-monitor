import json
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.nasa.config import NasaSettings
from hub.nasa.donki_cache import DonkiCache
from hub.nasa.dose import DoseProfile, DoseWriter, estimate_dose
from hub.nasa.routes import router
from hub.nasa.state import NasaState

METHOD = "mission_day × 0.5 mSv/day (upper ISS effective-dose rate, NTRS 20250006168); estimate, not measured"
S = {"n": 3, "mean": 2.0, "min": 1.0, "max": 3.0}


def _snap(mission="RR-6", co2=None, absorbed=10.0):
    cabin = {"temperature_c": S, "rh_pct": S}
    cabin.update(co2 or {"co2_mmhg": None, "co2_raw": {**S, "mean": 3250.0}, "co2_raw_unit": "ppm"})
    return {
        "fetched_at": "2026-11-14T10:00:00Z",
        "mission": mission,
        "source_urls": ["u"],
        "cabin": cabin,
        "dose": {
            "source": "eda",
            "absorbed_mgy": absorbed,
            "absorbed_mgy_per_day": 0.2,
            "raw_sum": absorbed,
            "raw_unit": "mGy/day",
        },
    }


def _writer(status="ok"):
    p = DoseProfile("ISS ref", date(2026, 5, 19), 0.5, "NTRS 20250006168", "u", METHOD, 600, "ref")
    w = DoseWriter(p, None)
    w.last = estimate_dose(p, date(2026, 11, 14))
    w.last_status = status
    return w


def _client(tmp_path, snap=None, dose=None, path=None):
    f = path or tmp_path / "snap.json"
    if snap is not None:
        f.write_text(json.dumps(snap))
    settings = NasaSettings(var_dir=tmp_path, osdr_snapshot_path=f)
    app = FastAPI()
    app.include_router(router)
    app.state.nasa = NasaState(
        settings,
        DonkiCache(tmp_path / "n"),
        lambda: datetime(2026, 11, 14, 12, tzinfo=UTC),
        ("c1",),
        dose=dose,
    )
    return TestClient(app)


def test_reference_from_snapshot_and_estimate(tmp_path):
    r = _client(tmp_path, _snap(), _writer()).get("/api/nasa/iss-reference")
    assert r.status_code == 200
    b = r.json()
    d = b["dose"]
    assert (d["absorbed_mgy"], d["effective_msv"], d["effective_msv_method"], d["status"]) == (
        10.0,
        90.0,
        METHOD,
        "ok",
    )
    assert (d["mission_day"], d["career_limit_msv"], d["career_fraction"]) == (180, 600, 0.15)
    assert b["label"] == "snapshot" and b["mission"] == "RR-6"
    assert b["snapshot_date"] == "2026-11-14T10:00:00Z" and b["source_urls"] == ["u"]


def test_absorbed_never_added_to_effective(tmp_path):
    d = _client(tmp_path, _snap(), _writer()).get("/api/nasa/iss-reference").json()["dose"]
    assert d["effective_msv"] == 90.0


def test_no_dose_writer(tmp_path):
    d = _client(tmp_path, _snap()).get("/api/nasa/iss-reference").json()["dose"]
    assert d["absorbed_mgy"] == 10.0 and d["status"] == "unknown"
    for k in ("effective_msv", "effective_msv_method", "profile", "mission_day", "career_fraction"):
        assert d[k] is None


def test_unit_suffixes(tmp_path):
    d = _client(tmp_path, _snap(), _writer()).get("/api/nasa/iss-reference").json()["dose"]
    for k, v in d.items():
        if isinstance(v, (int, float)) and k != "mission_day" and not isinstance(v, bool):
            assert k.endswith(("_mgy", "_mgy_per_day", "_msv", "_fraction")), k


def test_snapshot_missing_keeps_dose(tmp_path):
    b = _client(tmp_path, None, _writer()).get("/api/nasa/iss-reference").json()
    assert b["cabin"] is None and b["dose"]["absorbed_mgy"] is None
    assert b["dose"]["effective_msv"] == 90.0


def test_co2_raw_passthrough(tmp_path):
    c = _client(tmp_path, _snap()).get("/api/nasa/iss-reference").json()["cabin"]
    assert c["co2_mmhg"] is None and c["co2_raw"]["mean"] == 3250.0 and c["co2_raw_unit"] == "ppm"
    mm = _snap(co2={"co2_mmhg": S})
    c = _client(tmp_path, mm).get("/api/nasa/iss-reference").json()["cabin"]
    assert c["co2_mmhg"]["n"] == 3 and c["co2_raw"] is None and c["co2_raw_unit"] is None


def test_snapshot_path_from_settings(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_snap("AAA")))
    b = _client(tmp_path, _snap("BBB"), path=tmp_path / "b.json").get("/api/nasa/iss-reference")
    assert b.json()["mission"] == "BBB"


def test_snapshot_reread_on_change(tmp_path):
    c = _client(tmp_path, _snap("ONE"))
    assert c.get("/api/nasa/iss-reference").json()["mission"] == "ONE"
    (tmp_path / "snap.json").write_text(json.dumps(_snap("TWO")) + "\n")
    assert c.get("/api/nasa/iss-reference").json()["mission"] == "TWO"


def test_nothing_available_503(tmp_path):
    r = _client(tmp_path).get("/api/nasa/iss-reference")
    assert r.status_code == 503 and r.json() == {"reason": "no_reference_data"}


@pytest.mark.parametrize("bad", ["not json", "[]"])
def test_bad_snapshot_is_treated_as_missing(tmp_path, bad):
    f = tmp_path / "snap.json"
    f.write_text(bad)
    assert _client(tmp_path, None, path=f).get("/api/nasa/iss-reference").status_code == 503
