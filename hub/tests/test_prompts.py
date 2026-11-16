from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.prompts import PROMPT_ASKS
from hub.tests.helpers import FOOD_RULES, MAIN_RULES, msg

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


@pytest.fixture
def client(settings, clock):
    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    app = create_app(s, clock=clock)
    frames = []
    app.state.bus.publish_orig = app.state.bus.publish
    with TestClient(app) as c:
        c.n = 0
        c.frames = frames
        c.svc = app.state.prompts
        orig = c.svc.emit
        c.svc.emit = lambda t, d: (frames.append((t, d)), orig(t, d))
        yield c


def temp(c, val, **kw):
    c.n += 1
    body = msg(seq=c.n, ind="cabin_temp", unit="C", val=val, dev="BME280", **kw)
    assert c.post("/api/readings", json=body).status_code == 201


def test_morning_not_before_time(client):
    assert client.svc.tick(datetime(2026, 11, 14, 9, 59, tzinfo=UTC)) == []


def test_morning_at_time(client):
    ps = client.svc.tick(datetime(2026, 11, 14, 10, 0, tzinfo=UTC))
    assert sorted(p.crew for p in ps) == ["crew-a", "crew-b", "crew-c"]
    p = ps[0]
    assert (p.kind, p.asks, p.status, p.trigger_reading_id, p.rule_id, p.trigger) == (
        "morning", ["body_temp", "hr", "sleep_h", "mood"], "open", None, None, None,
    )  # fmt: skip
    assert client.svc.tick(datetime(2026, 11, 14, 10, 0, 30, tzinfo=UTC)) == []


def test_morning_next_day_skips_old(client):
    client.svc.tick(datetime(2026, 11, 14, 10, 0, tzinfo=UTC))
    client.frames.clear()
    client.svc.tick(datetime(2026, 11, 15, 10, 0, tzinfo=UTC))
    allp = client.svc.pending("crew-a", "all")
    assert [p.status for p in allp if p.crew == "crew-a"] == ["skipped", "open"]
    assert len(client.frames) == 6 and {t for t, _ in client.frames} == {"prompt"}


def test_cabin_trigger_on_watch_and_dedupe(client):
    temp(client, 22.0)
    temp(client, 26.0)
    (p,) = client.svc.pending(None)
    assert (p.kind, p.asks, p.crew, p.rule_id) == (
        "cabin_trigger", ["symptom"], None, "cabin_performance_temp",
    )  # fmt: skip
    assert p.trigger["status"] == "watch" and p.trigger["reading_id"] == p.trigger_reading_id
    assert ("prompt", p.to_dict()) in client.frames
    temp(client, 26.5)
    assert len(client.svc.pending(None)) == 1


def test_no_trigger_for_body_or_ok_or_intake(client):
    client.n += 1
    hr = msg(node="vitals-1", seq=client.n, ind="hr", unit="bpm", val=110, dev="MAX30102")
    client.post("/api/readings", json=hr)
    temp(client, 26.0)
    n = len(client.svc.pending(None))
    temp(client, 22.0)  # back to ok
    f = {"node": "food", "src": "self", "dev": "catalog", "ind": "intake_sodium_mg", "unit": "mg"}
    client.n += 1
    client.post("/api/readings", json=msg(seq=client.n, val=2400, crew="crew-a", **f))
    assert len(client.svc.pending(None)) == n == 1


def test_post_exercise(client):
    client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81, "crew": "crew-a"})
    client.post("/api/sessions/s1/end")
    (p,) = client.svc.pending(None)
    assert (p.kind, p.crew, p.asks) == ("post_exercise", "crew-a", ["hr", "symptom"])


def test_pending_filter_and_status_all(client):
    a = client.svc.create("morning", "crew-a")
    b = client.svc.create("morning", "crew-b")
    n = client.svc.create("post_exercise", None)
    c2 = client.svc.create("morning", "crew-a")
    client.svc.answer(c2.id, [], skipped=True)
    got = client.get("/api/prompts?crew=crew-a").json()
    assert [p["id"] for p in got] == [a.id, n.id]
    assert [p["id"] for p in client.get("/api/prompts").json()] == [a.id, b.id, n.id]
    allp = client.get("/api/prompts?crew=crew-a&status=all").json()
    assert [p["status"] for p in allp] == ["open", "open", "skipped"]
    assert client.get("/api/prompts?status=answered").json() == {"reason": "bad_value:status"}


def test_manual_create(client):
    r = client.post("/api/prompts", json={"kind": "morning", "crew": "crew-b"})
    assert r.status_code == 201 and r.json()["status"] == "open"
    assert client.post("/api/prompts", json={"kind": "lunch", "crew": None}).json() == {
        "reason": "bad_value:kind"
    }
    assert client.post("/api/prompts", json={"kind": "morning", "crew": "crew-z"}).json() == {
        "reason": "bad_crew"
    }
    assert set(PROMPT_ASKS) == {
        "morning", "post_exercise", "cabin_trigger", "signal_cabin", "signal_body",
    }  # fmt: skip
    # Signal prompts are opened only by the signals trigger, with a snapshot (D45 §8.2).
    assert client.post("/api/prompts", json={"kind": "signal_body", "crew": "crew-a"}).json() == {
        "reason": "bad_value:kind"
    }
