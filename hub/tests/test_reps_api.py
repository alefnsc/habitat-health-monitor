from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.exercise import align, latest_reps, work_cell_j
from hub.tests.helpers import msg

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def rep(src="camera", n=1, seq=1, peak=120.0, rom=0.5, node=None, session="s1", **kw):
    return {
        "v": 1, "node": node or ("camera" if src == "camera" else "exercise-1"), "boot": 7,
        "seq": seq, "age_ms": 0, "type": "rep", "session": session, "rep": n, "src": src,
        "peak_n": peak, "work_j": 45.0 if src == "camera" else None,
        "rom_m": rom if src == "camera" else None, "g": 9.81, "mass_kg": 10,
        "t0_ms": 1000, "t1_ms": 1400, **kw,
    }  # fmt: skip


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        c.n = 0
        yield c


def post_rep(c, **kw):
    c.n += 1
    r = c.post("/api/reps", json=rep(seq=kw.pop("seq", c.n), **kw))
    assert r.status_code == 201, r.text


def start(c, mass=10, session="s1"):
    assert (
        c.post("/api/sessions", json={"session": session, "mass_kg": mass, "g": 9.81}).status_code
        == 201
    )


def raw(c, at, force, seq, **kw):
    m = msg(
        node="exercise-1", boot=1, seq=seq, ind="load_raw", unit="N", val=force, dev="HX711", **kw
    )
    c.app.state.ingestor.clock = lambda: at
    assert c.post("/api/readings", json=m).status_code == 201


def test_align_by_rep_number(client):
    start(client)
    for n, p in ((1, 120), (2, 125), (3, 130)):
        post_rep(client, n=n, peak=p)
    for n, p in ((1, 118), (2, 126)):
        post_rep(client, src="load_cell", n=n, peak=p)
    body = client.get("/api/reps?session=s1").json()
    assert body["session"] == "s1" and [p["rep"] for p in body["pairs"]] == [1, 2, 3]
    assert body["pairs"][2]["load_cell"] is None and body["pairs"][2]["work_cell_j"] is None
    assert body["pairs"][1]["load_cell"]["peak_n"] == 126


def test_latest_seq_wins(client):
    post_rep(client, n=2, seq=5, peak=125)
    post_rep(client, n=2, seq=9, peak=127)
    assert client.get("/api/reps?session=s1").json()["pairs"][0]["camera"]["peak_n"] == 127


def test_latest_reps(client):
    for kw in ({"seq": 5}, {"seq": 9}, {"seq": 3, "src": "load_cell"}):
        post_rep(client, n=2, **kw)
    got = latest_reps(client.app.state.store.reps_for_session("s1"))
    assert sorted((r.src, r.seq) for r in got) == [("camera", 9), ("load_cell", 3)]
    pairs = align([r for r in got if r.src == "camera"], [r for r in got if r.src != "camera"])
    assert pairs[0][0] == 2 and pairs[0][1].seq == 9 and pairs[0][2].seq == 3


def work_setup(client, n_static, flagged=0):
    start(client)
    seq = 0
    for i in range(n_static):
        seq += 1
        raw(client, T + timedelta(milliseconds=i * 10), 100.0, seq)
    for i in range(flagged):
        seq += 1
        raw(client, T + timedelta(milliseconds=500 + i), 900.0, seq, q=["out_of_range"])
    post_rep(client, src="load_cell", n=1)
    post_rep(client, n=1, rom=0.5)
    return client.get("/api/reps?session=s1").json()["pairs"][0]


def test_work_cell(client, clock):
    start(client)
    seq = 0
    for i in range(100):
        seq += 1
        raw(client, T + timedelta(milliseconds=i * 10), 100.0, seq)
    for i in range(40):
        seq += 1
        raw(client, T + timedelta(milliseconds=1000 + i * 10), 110.0 if i % 2 == 0 else 130.0, seq)
    post_rep(client, src="load_cell", n=1)
    post_rep(client, n=1, rom=0.5)
    assert client.get("/api/reps?session=s1").json()["pairs"][0]["work_cell_j"] == 50.0


def test_work_cell_fallback(client):
    assert work_setup(client, 20)["work_cell_j"] == pytest.approx(49.05, abs=1e-9)


def test_work_cell_flagged(client):
    assert work_setup(client, 70, flagged=30)["work_cell_j"] == 50.0


def test_work_cell_nulls(client):
    start(client)
    post_rep(client, src="load_cell", n=1)
    post_rep(client, n=1, rom=None)
    assert client.get("/api/reps?session=s1").json()["pairs"][0]["work_cell_j"] is None
    store = client.app.state.store
    cam = store.reps_for_session("s1")
    c = next(r for r in cam if r.src == "camera")
    assert work_cell_j(store, None, None, c) is None
    assert work_cell_j(store, client.app.state.sessions.get("s1"), None, c) is None


def test_camera_only_session(client):
    post_rep(client, n=1, session="s9")
    b = client.get("/api/reps?session=s9")
    assert b.status_code == 200
    p = b.json()["pairs"][0]
    assert p["load_cell"] is None and p["work_cell_j"] is None


def test_unknown_and_missing(client):
    r = client.get("/api/reps?session=nope")
    assert r.status_code == 404 and r.json() == {"reason": "unknown_session"}
    r = client.get("/api/reps")
    assert r.status_code == 422 and r.json()["reason"] == "missing_field:session"


def test_sim_reps_included(client):
    post_rep(client, n=1, node="sim-1")
    p = client.get("/api/reps?session=s1").json()["pairs"][0]
    assert p["camera"]["node"] == "sim-1"
    assert client.get("/api/sessions").json() == []  # no session row, reps still counted above


def test_reps_between(client):
    store = client.app.state.store
    from hub.contract import parse_rep

    for i, h in enumerate((25, 23, 0)):
        node = "sim-1" if i == 2 else "camera"
        store.insert_rep(parse_rep(rep(n=i + 1, seq=i + 1, node=node)), T - timedelta(hours=h))
    got = store.reps_between(T - timedelta(hours=24), T)
    assert [r.rep for r in got] == [2, 3] and got[1].node == "sim-1"
    store.insert_rep(parse_rep(rep(n=9, seq=9)), T - timedelta(hours=24))
    assert 9 not in [r.rep for r in store.reps_between(T - timedelta(hours=24), T)]
