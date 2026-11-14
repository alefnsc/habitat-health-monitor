from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.nasa.config import NasaSettings
from hub.nasa.donki import DonkiResult
from hub.nasa.donki_cache import DonkiCache
from hub.nasa.routes import router
from hub.nasa.spaceweather import space_weather_state
from hub.nasa.state import NasaState

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
REPLAY = Path(__file__).resolve().parents[2] / "data" / "nasa" / "donki_replay_2025-11.json"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _client(tmp_path, *, mode="live", now=NOW, policy=None):
    settings = NasaSettings(var_dir=tmp_path, donki_mode=mode, replay_path=REPLAY)
    cache = DonkiCache(tmp_path / "nasa")
    app = FastAPI()
    app.include_router(router)
    clock = Clock(now)
    app.state.nasa = NasaState(settings, cache, clock, ("crew1",), policy=policy)
    return TestClient(app), cache, settings, clock


def _put(cache, kind, at, events=None):
    cache.write(DonkiResult(kind, events or [], "direct", at))


def _fill(cache, at, sep=None):
    for k in ("FLR", "GST", "notifications"):
        _put(cache, k, at)
    _put(cache, "SEP", at, sep)


SEP = [{"sepID": "s1", "eventTime": "2026-11-14T10:00Z", "link": "https://x", "extra": 1}]


def test_no_cache_is_unknown(tmp_path):
    c, *_ = _client(tmp_path)
    b = c.get("/api/nasa/space-weather").json()
    assert (b["status"], b["cached_at"], b["stale"], b["mode"], b["ack"]) == (
        "unknown",
        None,
        False,
        "live",
        None,
    )


def test_fresh_cache_with_sep_is_act(tmp_path):
    c, cache, *_ = _client(tmp_path)
    _fill(cache, datetime(2026, 11, 14, 11, 50, tzinfo=UTC), SEP)
    b = c.get("/api/nasa/space-weather").json()
    assert (b["status"], b["rule_id"], b["stale"]) == ("act", "radiation_spe", False)
    assert b["cached_at"] == "2026-11-14T11:50:00Z"
    assert b["event_id"] == "s1" and b["route"] == "direct"
    assert set(b["events"]) == {"FLR", "SEP", "GST", "notifications"}


def test_stale_cache_reports_unknown_but_keeps_events(tmp_path):
    c, cache, settings, clock = _client(tmp_path, now=datetime(2026, 11, 14, 12, 21, tzinfo=UTC))
    _fill(cache, datetime(2026, 11, 14, 11, 50, tzinfo=UTC), SEP)
    b = c.get("/api/nasa/space-weather").json()
    assert b["stale"] is True and b["status"] == "unknown" and len(b["events"]["SEP"]) == 1
    st = space_weather_state(clock(), settings=settings, cache=cache)
    assert st.level == 2


def test_cached_at_is_oldest_kind(tmp_path):
    c, cache, *_ = _client(tmp_path, now=datetime(2026, 11, 14, 11, 45, tzinfo=UTC))
    _fill(cache, datetime(2026, 11, 14, 11, 50, tzinfo=UTC))
    _put(cache, "SEP", datetime(2026, 11, 14, 11, 20, tzinfo=UTC))
    b = c.get("/api/nasa/space-weather").json()
    assert b["cached_at"] == "2026-11-14T11:20:00Z" and b["stale"] is False


def test_replay_mode(tmp_path):
    c, *_ = _client(tmp_path, mode="replay")
    b = c.get("/api/nasa/space-weather").json()
    assert (b["mode"], b["status"], b["stale"]) == ("replay", "act", False)
    assert b["cached_at"].startswith("2026-11-14T")  # the replay's recorded_at, not the clock
    assert b["event_time"].startswith("2025-11-10")


def test_events_are_trimmed(tmp_path):
    c, cache, *_ = _client(tmp_path)
    flr = [
        {
            "flrID": f"f{i}",
            "beginTime": "b",
            "peakTime": f"2026-11-{i % 14 + 1:02d}T00:00Z",
            "endTime": "e",
            "classType": "C1.0",
            "link": "l",
            "junk": 1,
        }
        for i in range(40)
    ]
    _fill(cache, NOW - timedelta(minutes=5))
    _put(cache, "FLR", NOW - timedelta(minutes=5), flr)
    got = c.get("/api/nasa/space-weather").json()["events"]["FLR"]
    assert len(got) == 10
    assert set(got[0]) == {"flrID", "beginTime", "peakTime", "endTime", "classType", "link"}
    peaks = [g["peakTime"] for g in got]
    assert peaks == sorted(peaks, reverse=True)


def test_disclaimer_present(tmp_path):
    c, *_ = _client(tmp_path)
    d = c.get("/api/nasa/space-weather").json()["disclaimer"]
    assert "research" in d and "NOAA SWPC" in d


def test_ack_null_without_policy(tmp_path):
    c, *_ = _client(tmp_path)
    assert c.get("/api/nasa/space-weather").json()["ack"] is None


def test_ack_comes_from_policy(tmp_path):
    class P:
        ack: ClassVar[dict] = {"acked_by": "crew1"}

    c, *_ = _client(tmp_path, policy=P())
    assert c.get("/api/nasa/space-weather").json()["ack"] == {"acked_by": "crew1"}


@pytest.mark.parametrize("path", ["/api/nasa/space-weather"])
def test_no_network_at_request_time(tmp_path, path):
    import respx

    c, *_ = _client(tmp_path)
    with respx.mock(assert_all_called=False) as r:
        c.get(path)
        assert r.calls.call_count == 0
