import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import FOOD_RULES, MAIN_RULES, msg


@pytest.fixture
def app(settings, clock):
    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    return create_app(s, clock=clock)


def temp(seq, val, **kw):
    return msg(seq=seq, ind="cabin_temp", unit="C", val=val, dev="BME280", **kw)


def test_snapshot_on_connect(app):
    with TestClient(app) as c:
        c.post("/api/readings", json=temp(1, 22.0))
        with c.websocket_connect("/ws") as ws:
            f = ws.receive_json()
        assert f["type"] == "snapshot"
        body = c.get("/api/status").json()
        assert {**f["data"], "generated_at": 0} == {**body, "generated_at": 0}


def test_push_order(app):
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        c.post("/api/readings", json=temp(1, 26.0))
        a = ws.receive_json()
        assert a["type"] == "assessment"
        d = a["data"]
        assert (d["ind"], d["val"], d["status"], d["rule_id"]) == (
            "cabin_temp", 26.0, "watch", "cabin_performance_temp",
        )  # fmt: skip
        al = ws.receive_json()
        assert al["type"] == "alert"
        assert (al["data"]["rule_id"], al["data"]["status"], al["data"]["prev_status"]) == (
            "cabin_performance_temp", "watch", None,
        )  # fmt: skip
        assert app.state.bus.subscribers


def test_two_clients(app):
    with TestClient(app) as c, c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.receive_json()
        b.receive_json()
        c.post("/api/readings", json=temp(1, 22.0))
        assert a.receive_json() == b.receive_json()


def test_disconnected_client_harmless(app):
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
        r = c.post("/api/readings", json=temp(1, 22.0))
        assert r.status_code == 201
        assert len(app.state.bus.subscribers) == 0


def test_flagged_reading_frames(app):
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        c.post("/api/readings", json=temp(1, 26.0, q=["no_contact"]))
        f = ws.receive_json()
        d = f["data"]
        assert (f["type"], d["status"], d["rule_id"], d["q"]) == (
            "assessment", "unknown", None, ["no_contact"],
        )  # fmt: skip
        c.post("/api/readings", json=temp(2, 22.0))
        assert ws.receive_json()["type"] == "assessment"  # next frame is the next reading's


def test_load_raw_not_pushed(app):
    raw = msg(node="exercise-1", boot=1, seq=1, ind="load_raw", unit="N", val=100, dev="HX711")
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        c.post("/api/readings", json=raw)
        c.post("/api/readings", json=temp(1, 22.0))
        assert ws.receive_json()["data"]["ind"] == "cabin_temp"


def test_node_change_snapshot(app):
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        threading.Thread(
            target=lambda: app.state.nodes.set_online("cabin-1", False, app.state.clock())
        ).start()
        f = ws.receive_json()
        assert f["type"] == "snapshot"
        assert f["data"]["nodes"][0]["online"] is False


def test_unknown_type_rejected(app):
    with pytest.raises(ValueError):
        app.state.bus.publish("reading", {})


def test_thread_publish(app):
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        t = threading.Thread(target=lambda: app.state.bus.publish("link", {"state": "contact"}))
        t.start()
        assert ws.receive_json() == {"type": "link", "data": {"state": "contact"}}
