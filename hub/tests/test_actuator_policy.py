from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.nasa.actuator import ActuatorPolicy, NoActiveAlert
from hub.nasa.config import NasaSettings
from hub.nasa.donki_cache import DonkiCache
from hub.nasa.routes import router
from hub.nasa.spaceweather import SpaceWeatherAlert, SpaceWeatherState
from hub.nasa.state import NasaState

REPLAY = Path(__file__).resolve().parents[2] / "data" / "nasa" / "donki_replay_2025-11.json"
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def at(minute):
    return datetime(2026, 11, 14, 12, minute, tzinfo=UTC)


class FakeRouter:
    def __init__(self):
        self.sent = []

    def send(self, node, cmd):
        self.sent.append((node, cmd))


class FakeIngestor:
    def __init__(self):
        self.readings = []

    def ingest_internal(self, r):
        self.readings.append(r)


def st(status, level, event_id=None, stale=False, mode="live"):
    alert = SpaceWeatherAlert(status, level, event_id=event_id)
    return SpaceWeatherState(alert, level, mode, None, stale, None, {})


ACT1, ACT2 = st("act", 2, "E1"), st("act", 2, "E2")
OK, WATCH = st("ok", 0), st("watch", 1)


def make(tmp_path, router_=True, mode="live"):
    r, i = (FakeRouter() if router_ else None), FakeIngestor()
    settings = NasaSettings(var_dir=tmp_path, donki_mode=mode, replay_path=REPLAY)
    p = ActuatorPolicy(
        r, i, settings=settings, cache=DonkiCache(tmp_path / "n"), crews=("crew-a", "crew-b")
    )
    return p, r, i, settings


def cmds(r):
    return [(c.cmd, c.angle_deg, c.on) for _, c in r.sent]


def test_ok_to_act_moves_servo_and_sounds_alarm(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(OK, at(0))
    r.sent.clear()
    p.apply(ACT1, T0)
    assert cmds(r) == [("servo", 150, None), ("alarm", None, True)]
    assert all(n == "exercise-1" and c.v == 1 for n, c in r.sent)
    x = i.readings[-1]
    assert (x.node, x.boot, x.seq, x.age_ms, x.ind, x.val, x.unit, x.src, x.dev, x.q, x.crew) == (
        "nasa",
        0,
        1794657600000,
        0,
        "space_weather",
        2,
        "level",
        "nasa",
        "DONKI",
        ("ok",),
        None,
    )


def test_repeat_act_same_event_sends_nothing(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(ACT1, T0)
    r.sent.clear()
    p.apply(ACT1, at(10))
    assert r.sent == [] and len(i.readings) == 2
    assert i.readings[-1].val == 2 and i.readings[-1].seq == 1794658200000


def test_badge_ack_silences_alarm_only(tmp_path):
    p, r, *_ = make(tmp_path)
    p.apply(ACT1, T0)
    r.sent.clear()
    p.on_badge("cabin-1", "crew-b", at(5))
    assert cmds(r) == [("alarm", None, False)]
    assert (p.ack.crew, p.ack.at, p.ack.event_id) == ("crew-b", at(5), "E1")


def test_ack_survives_next_tick(tmp_path):
    p, r, *_ = make(tmp_path)
    p.apply(ACT1, T0)
    p.on_badge("cabin-1", "crew-b", at(5))
    r.sent.clear()
    p.apply(ACT1, at(10))
    assert r.sent == [] and p.ack is not None


def test_new_event_rearms(tmp_path):
    p, r, *_ = make(tmp_path)
    p.apply(ACT1, T0)
    p.on_badge("cabin-1", "crew-b", at(5))
    r.sent.clear()
    p.apply(ACT2, at(10))
    assert cmds(r) == [("alarm", None, True)] and p.ack is None


def test_act_to_ok_resets(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(ACT1, T0)
    r.sent.clear()
    p.apply(OK, at(10))
    assert cmds(r) == [("servo", 30, None), ("alarm", None, False)]
    assert p.ack is None and i.readings[-1].val == 0


def test_watch_moves_servo_no_alarm(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(OK, at(0))
    r.sent.clear()
    p.apply(WATCH, at(1))
    assert cmds(r) == [("servo", 90, None)] and i.readings[-1].val == 1


def test_stale_keeps_latched_alarm_and_flags_reading(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(ACT1, T0)
    r.sent.clear()
    p.apply(st("unknown", 2, stale=True), at(40))
    assert cmds(r) == [("servo", 0, None)]
    assert i.readings[-1].val == 2 and i.readings[-1].q == ("stale",)
    r.sent.clear()
    p.on_badge("cabin-1", "crew-a", at(41))  # a stale link must not block the ack
    assert cmds(r) == [("alarm", None, False)]


def test_no_cache_writes_no_reading(tmp_path):
    p, r, i, _ = make(tmp_path)
    p.apply(st("unknown", None), T0)
    assert cmds(r) == [("servo", 0, None)] and i.readings == []


def _client(p, settings):
    app = FastAPI()
    app.include_router(router)
    app.state.nasa = NasaState(settings, p.cache, lambda: at(7), ("crew-a", "crew-b"), policy=p)
    return TestClient(app)


def test_replay_reading_is_labelled(tmp_path):
    p, _, i, settings = make(tmp_path, mode="replay")
    p.apply(st("act", 2, "E1", mode="replay"), T0)
    assert i.readings[-1].src == "nasa"
    body = _client(p, settings).get("/api/nasa/space-weather").json()
    assert body["mode"] == "replay"


def test_badge_outside_alert_is_ignored(tmp_path):
    p, r, *_ = make(tmp_path)
    p.apply(OK, T0)
    r.sent.clear()
    assert p.on_badge("cabin-1", "crew-a", at(1)) == [] and p.ack is None and r.sent == []


def test_unknown_badge_crew_is_ignored(tmp_path):
    p, r, *_ = make(tmp_path)
    p.apply(ACT1, T0)
    r.sent.clear()
    assert p.on_badge("cabin-1", "unknown", at(1)) == [] and p.ack is None and r.sent == []


def test_no_router_still_writes_reading(tmp_path):
    p, _, i, _ = make(tmp_path, router_=False)
    assert p.apply(ACT1, T0) == []
    assert i.readings[-1].val == 2
    p.acknowledge("crew-a", at(1))


def test_router_failure_is_logged_not_raised(tmp_path):
    p, r, i, _ = make(tmp_path)

    def boom(*a):
        raise OSError("serial gone")

    r.send = boom
    p.apply(ACT1, T0)
    assert i.readings


def test_acknowledge_without_alert_raises(tmp_path):
    p, *_ = make(tmp_path)
    with pytest.raises(NoActiveAlert):
        p.acknowledge("crew-a", T0)


def test_ack_endpoint_409_without_alert(tmp_path):
    p, _, _, s = make(tmp_path)
    p.apply(OK, T0)
    r = _client(p, s).post("/api/nasa/space-weather/ack", json={"crew": "crew-a"})
    assert r.status_code == 409 and r.json() == {"reason": "no_active_alert"}


def test_ack_endpoint_ok(tmp_path):
    p, rt, _, s = make(tmp_path)
    p.apply(ACT1, T0)
    rt.sent.clear()
    c = _client(p, s)
    r = c.post("/api/nasa/space-weather/ack", json={"crew": "crew-a"})
    assert r.status_code == 200
    assert r.json()["ack"]["crew"] == "crew-a" and r.json()["ack"]["event_id"] == "E1"
    assert cmds(rt) == [("alarm", None, False)]
    assert c.get("/api/nasa/space-weather").json()["ack"]["crew"] == "crew-a"


def test_ack_endpoint_rejects_unknown_crew(tmp_path):
    p, _, _, s = make(tmp_path)
    p.apply(ACT1, T0)
    r = _client(p, s).post("/api/nasa/space-weather/ack", json={"crew": "crew-z"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tick_replay_drill_end_to_end(tmp_path):
    p, r, i, _ = make(tmp_path, mode="replay")
    await p.tick(T0)
    assert cmds(r) == [("servo", 150, None), ("alarm", None, True)]
    assert i.readings[-1].val == 2
