import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.nasa.config import NasaSettings
from hub.nasa.donki_cache import DonkiCache
from hub.nasa.isslive import IssLiveState
from hub.nasa.routes import router
from hub.nasa.state import NasaState

NOW = datetime(2026, 11, 14, 12, 0, 42, tzinfo=UTC)


def ts_for(t: datetime) -> str:
    doy = t.timetuple().tm_yday
    return str(doy * 24 + t.hour + t.minute / 60 + t.second / 3600)


def _client(tmp_path, iss, capture: list[dict] | None = None):
    cap = tmp_path / "capture.jsonl"
    if capture is not None:
        cap.write_text("\n".join(json.dumps(c) for c in capture))
    settings = NasaSettings(var_dir=tmp_path, isslive_capture=cap)
    app = FastAPI()
    app.include_router(router)
    app.state.nasa = NasaState(settings, DonkiCache(tmp_path / "nasa"), lambda: NOW, ("crew1",), iss=iss)
    return TestClient(app)


def _live(items: dict[str, tuple[float, datetime]], connected=True):
    s = IssLiveState()
    for item, (val, measured) in items.items():
        s.update(item, ts_for(measured), str(val), "Normal", measured)
    s.connected = connected
    return s


def _by_name(body):
    return {i["name"]: i for i in body["items"]}


def test_live_item_age(tmp_path):
    m = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
    body = _client(tmp_path, _live({"USLAB000058": (759.26, m)})).get("/api/nasa/iss-cabin").json()
    p = _by_name(body)["cabin_pressure"]
    assert body["mode"] == "live"
    assert (p["val"], p["unit"], p["val_hpa"], p["age_s"], p["stale"]) == (759.26, "mmHg", 1012.26, 42, False)


def test_temperature_has_no_hpa(tmp_path):
    m = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
    body = _client(tmp_path, _live({"USLAB000059": (23.26, m)})).get("/api/nasa/iss-cabin").json()
    t = _by_name(body)["cabin_temperature"]
    assert t["unit"] == "C" and t["val_hpa"] is None
    assert len(body["items"]) == 1  # unseen items are omitted


def test_old_item_is_stale_but_live(tmp_path):
    old = NOW - timedelta(days=11)
    body = _client(tmp_path, _live({"USLAB000055": (2.44, old)})).get("/api/nasa/iss-cabin").json()
    i = _by_name(body)["lab_ppco2"]
    assert body["mode"] == "live" and i["stale"] is True and i["age_s"] >= 950400


CAPTURE = [
    {"item": "USLAB000058", "val": 759.10, "ts": float(ts_for(datetime(2026, 11, 14, 11, 50, tzinfo=UTC))),
     "status_class": "Normal", "received_at": "2026-11-14T11:50:05.000Z"},
]


def test_disconnected_uses_capture(tmp_path):
    s = _live({"USLAB000058": (759.26, NOW)}, connected=False)
    s.last_connected_at = NOW - timedelta(seconds=150)
    body = _client(tmp_path, s, CAPTURE).get("/api/nasa/iss-cabin").json()
    p = _by_name(body)["cabin_pressure"]
    assert body["mode"] == "recorded" and body["recorded_at"] == "2026-11-14T11:50:05Z"
    assert p["val"] == 759.10 and p["age_s"] == 642


def test_recently_dropped_is_still_live(tmp_path):
    s = _live({"USLAB000058": (759.26, NOW)}, connected=False)
    s.last_connected_at = NOW - timedelta(seconds=60)
    assert _client(tmp_path, s, CAPTURE).get("/api/nasa/iss-cabin").json()["mode"] == "live"


def test_never_connected_after_30s_uses_capture(tmp_path):
    s = IssLiveState()
    s.started_at = NOW - timedelta(seconds=31)
    assert _client(tmp_path, s, CAPTURE).get("/api/nasa/iss-cabin").json()["mode"] == "recorded"


def test_no_iss_state_uses_capture(tmp_path):
    assert _client(tmp_path, None, CAPTURE).get("/api/nasa/iss-cabin").json()["mode"] == "recorded"


def test_no_data_503(tmp_path):
    r = _client(tmp_path, None, None).get("/api/nasa/iss-cabin")
    assert r.status_code == 503 and r.json() == {"reason": "no_iss_data"}


def test_unit_note(tmp_path):
    body = _client(tmp_path, None, CAPTURE).get("/api/nasa/iss-cabin").json()
    assert "PSI" in body["unit_note"] and "mmHg by magnitude" in body["unit_note"]


def test_committed_capture_is_readable():
    p = Path(__file__).resolve().parents[2] / "data" / "nasa" / "isslive_capture.jsonl"
    if p.exists():
        assert {json.loads(x)["item"] for x in p.read_text().splitlines()}
