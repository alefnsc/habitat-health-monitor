import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import msg

CAM = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        yield c


def raw(c, clock, t_ms, force, seq, **kw):
    from datetime import timedelta

    base = clock()
    m = msg(
        node="exercise-1", boot=1, seq=seq, ind="load_raw", unit="N", val=force, dev="HX711", **kw
    )
    c.app.state.ingestor.clock = lambda: base + timedelta(milliseconds=t_ms)
    r = c.post("/api/readings", json=m)
    assert r.status_code == 201
    c.app.state.ingestor.clock = clock


def feed_rep(c, clock, end_low=True):
    seq = 0
    for t in range(0, 1000, 10):
        seq += 1
        raw(c, clock, t, 100.0, seq)
    for t in range(1000, 1500 if end_low else 1300, 10):
        seq += 1
        f = 130.0 if t == 1200 else (115.0 if t < 1400 else 100.0)
        raw(c, clock, t, f, seq)


def test_session_api(client):
    r = client.post("/api/sessions", json={"mass_kg": 10, "g": 9.81, "crew": "crew-a"})
    assert r.status_code == 201
    first = r.json()
    assert first == {
        "session": "s-1794657600000", "mass_kg": 10, "g": 9.81, "crew": "crew-a",
        "started_at": "2026-11-14T12:00:00.000Z", "ended_at": None, "camera_reps": 0,
        "load_cell_reps": 0,
    }  # fmt: skip
    assert (
        client.post("/api/sessions", json={"session": "s2", "mass_kg": 5, "g": 1.62}).status_code
        == 201
    )
    assert client.get("/api/sessions").json()[1]["ended_at"] is not None
    r = client.post("/api/sessions", json={"session": "s2", "mass_kg": 5, "g": 1.62})
    assert r.status_code == 409 and r.json() == {"reason": "session_exists"}
    r = client.post("/api/sessions/nope/end")
    assert r.status_code == 404 and r.json() == {"reason": "unknown_session"}
    a = client.post("/api/sessions/s-1794657600000/end")
    assert (
        a.status_code == 200 and a.json() == client.post("/api/sessions/s-1794657600000/end").json()
    )
    for body, reason in (
        ({"mass_kg": 0, "g": 9.81}, "bad_value:mass_kg"),
        ({"mass_kg": 1, "g": -1}, "bad_value:g"),
        ({"mass_kg": 1, "g": 1, "crew": "crew-z"}, "bad_crew"),
    ):
        r = client.post("/api/sessions", json=body)
        assert r.status_code == 422 and r.json()["reason"] == reason
    assert [s["session"] for s in client.get("/api/sessions").json()] == ["s2", "s-1794657600000"]


def test_rep_from_stream(client, clock):
    client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81})
    feed_rep(client, clock)
    (rep,) = client.app.state.store.reps_for_session("s1")
    assert (rep.node, rep.boot, rep.seq, rep.type, rep.session, rep.rep, rep.src) == (
        "exercise-1", 1, 1, "rep", "s1", 1, "load_cell",
    )  # fmt: skip
    assert (rep.peak_n, rep.work_j, rep.rom_m, rep.g, rep.mass_kg, rep.t0_ms, rep.t1_ms) == (
        130.0, None, None, 9.81, 10.0, 1000, 1400,
    )  # fmt: skip
    items = client.get("/api/outbox?limit=1000").json()["items"]
    assert [i["kind"] for i in items].count("rep") == 1
    assert client.get("/api/sessions").json()[0]["load_cell_reps"] == 1


def test_camera_rep_count(client):
    client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81})
    for seq, rep in ((1, 1), (2, 2), (3, 2)):
        assert client.post("/api/reps", json={**CAM, "seq": seq, "rep": rep}).status_code == 201
    assert client.get("/api/sessions").json()[0]["camera_reps"] == 2


def test_no_session_no_reps(client, clock):
    feed_rep(client, clock)
    assert client.app.state.store.count("reps") == 0
    assert client.app.state.store.count("readings") > 0


def test_end_mid_rep(client, clock):
    client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81})
    feed_rep(client, clock, end_low=False)
    s = client.post("/api/sessions/s1/end").json()
    assert s["load_cell_reps"] == 0


def test_flagged_samples_ignored(client, clock):
    client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81})
    seq = 0
    for t in range(0, 1000, 10):
        seq += 1
        raw(client, clock, t, 100.0, seq)
    for t in range(1000, 1500, 10):
        seq += 1
        f = 130.0 if t == 1200 else (115.0 if t < 1400 else 100.0)
        raw(client, clock, t, f, seq)
        seq += 1
        raw(client, clock, t, 900.0, seq, q=["out_of_range"])
    (rep,) = client.app.state.store.reps_for_session("s1")
    assert rep.peak_n == 130.0
