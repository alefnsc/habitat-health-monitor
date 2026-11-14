"""N modules wired by H19 into the real app (feature `nasa`), replay mode, no network."""

import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def app(settings, clock, monkeypatch, tmp_path):
    monkeypatch.setenv("DONKI_MODE", "replay")
    monkeypatch.setenv("HUB_VAR_DIR", str(tmp_path / "var"))
    s = replace(
        settings,
        features=frozenset({"nasa"}),
        thresholds_path=ROOT / "data" / "thresholds.json",
        guidance_path=ROOT / "data" / "guidance.json",
    )
    return create_app(s, clock=clock)


def _wait(client, ind, tries=50):
    for _ in range(tries):
        rows = client.get(f"/api/readings?ind={ind}&limit=1").json()
        rows = rows.get("readings", rows) if isinstance(rows, dict) else rows
        if rows:
            return rows[0]
        time.sleep(0.1)
    return None


def test_nasa_parts_load(app):
    assert not {k for k in app.state.features.skipped if k.startswith("nasa")}
    assert app.state.nasa.policy is not None and app.state.nasa.dose is not None


def test_replay_drill_through_real_pipeline(app):
    with TestClient(app) as c:
        sw = _wait(c, "space_weather")
        dose = _wait(c, "rad_dose_cum")
        assert sw and sw["val"] == 2 and sw["src"] == "nasa"
        assert dose and dose["unit"] == "mSv" and dose["node"] == "nasa"
        body = c.get("/api/nasa/space-weather").json()
        assert body["mode"] == "replay" and body["status"] == "act"
        status = c.get("/api/status").text
        assert "radiation_spe" in status and "radiation_career" in status
        ref = c.get("/api/nasa/iss-reference").json()
        assert ref["mission"] == "RR-6" and ref["dose"]["effective_msv_method"]
        assert ref["dose"]["status"] in ("ok", "watch", "act")
        ack = c.post("/api/nasa/space-weather/ack", json={"crew": app.state.nasa.crews[0]})
        assert ack.status_code == 200
