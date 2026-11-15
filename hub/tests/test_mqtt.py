import json

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.ingest import Ingestor
from hub.mqtt import NodeRegistry, route_message
from hub.store import Store
from hub.tests.helpers import msg

REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


@pytest.fixture
def rig(tmp_path, clock):
    store = Store(tmp_path / "m.db")
    return store, Ingestor(store, clock), NodeRegistry(clock)


def test_route_reading(rig, clock):
    _, ing, nodes = rig
    clock.advance(5)
    res = route_message(ing, nodes, "habitat/v1/r/cabin-1", json.dumps(msg(age_ms=5000)).encode())
    assert res.reason is None and res.stored.measured_at == "2026-11-14T12:00:00.000Z"
    (n,) = nodes.snapshot()
    assert (n.node, n.online, n.last_seen) == ("cabin-1", True, "2026-11-14T12:00:05.000Z")


def test_route_tilt_reading(rig):
    store, ing, nodes = rig
    raw = json.dumps(msg(node="tilt-1", ind="tilt", val=1, unit="state", dev="KY017")).encode()
    res = route_message(ing, nodes, "habitat/v1/r/tilt-1", raw)
    assert res.reason is None and res.stored is not None and store.count("readings") == 1
    assert nodes.snapshot()[0].node == "tilt-1"


def test_route_topic_mismatch(rig):
    store, ing, nodes = rig
    raw = json.dumps(msg(node="vitals-1", ind="hr", unit="bpm", dev="MAX30102")).encode()
    res = route_message(ing, nodes, "habitat/v1/r/cabin-1", raw)
    assert res.reason == "topic_node_mismatch" and store.count("readings") == 0


def test_route_too_large(rig):
    _, ing, nodes = rig
    raw = json.dumps(msg(pad="x" * 300)).encode()
    assert route_message(ing, nodes, "habitat/v1/r/cabin-1", raw).reason == "too_large"


def test_route_rep(rig):
    store, ing, nodes = rig
    res = route_message(ing, nodes, "habitat/v1/rep/camera", json.dumps(REP).encode())
    assert res.reason is None and store.count("reps") == 1


def test_route_status(rig, clock, caplog):
    _, ing, nodes = rig
    fired = []
    nodes.on_change(lambda: fired.append(1))
    assert route_message(ing, nodes, "habitat/v1/status/cabin-1", b"offline") is None
    (n,) = nodes.snapshot()
    assert (n.node, n.online, n.last_seen) == ("cabin-1", False, "2026-11-14T12:00:00.000Z")
    assert len(fired) == 1
    route_message(ing, nodes, "habitat/v1/status/cabin-1", b"offline")
    assert len(fired) == 1
    with caplog.at_level("INFO"):
        route_message(ing, nodes, "habitat/v1/status/cabin-1", b"rebooting")
    assert nodes.snapshot()[0].online is False and "rebooting" in caplog.text


def test_data_does_not_revive_offline_node(rig):
    _, ing, nodes = rig
    route_message(ing, nodes, "habitat/v1/status/cabin-1", b"offline")
    route_message(ing, nodes, "habitat/v1/r/cabin-1", json.dumps(msg()).encode())
    assert nodes.snapshot()[0].online is False


def test_route_unknown_topic(rig):
    store, ing, nodes = rig
    assert route_message(ing, nodes, "habitat/v2/r/cabin-1", json.dumps(msg()).encode()) is None
    assert store.count("readings") == 0


def test_route_extra_handler(rig):
    _, ing, nodes = rig
    got = []
    route_message(
        ing, nodes, "habitat/v1/badge/cabin-1", b"{}", {"badge": lambda n, p: got.append(n)}
    )
    assert got == ["cabin-1"]


def test_status_includes_nodes(settings, clock):
    app = create_app(settings, clock=clock)
    route_message(app.state.ingestor, app.state.nodes, "habitat/v1/r/cabin-1",
                  json.dumps(msg()).encode())  # fmt: skip
    with TestClient(app) as c:
        assert c.get("/api/status").json()["nodes"] == [
            {
                "node": "cabin-1",
                "online": True,
                "last_seen": "2026-11-14T12:00:00.000Z",
                "duplicates": 0,
                "clashes": 0,
            }
        ]


def tilt_raw(seq, val, age_ms=2):
    m = msg(node="tilt-1", boot=9, seq=seq, age_ms=age_ms, ind="tilt", val=val, unit="state",
            dev="KY017")  # fmt: skip
    return json.dumps(m).encode()


def test_registry_counts_duplicates_and_clashes(rig, clock):
    store, ing, nodes = rig
    route_message(ing, nodes, "habitat/v1/r/tilt-1", tilt_raw(1, 1))
    clock.advance(3)
    route_message(ing, nodes, "habitat/v1/r/tilt-1", tilt_raw(1, 1, age_ms=3002))  # node retry
    clock.advance(44 * 60)
    route_message(ing, nodes, "habitat/v1/r/tilt-1", tilt_raw(1, 0))  # repeated boot number
    (n,) = nodes.snapshot()
    assert (n.duplicates, n.clashes) == (1, 1) and store.count("readings") == 2
