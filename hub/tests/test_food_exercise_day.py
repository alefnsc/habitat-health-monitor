from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.food.day import exercise_day
from hub.food.routes import router
from hub.ingest import Ingestor
from hub.store import Store

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
MASS = 100.0 / 9.81  # static load F0 = 100.0 N


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path / "e.db")
    ing = Ingestor(store, lambda: T)
    yield store, ing
    store.close()


def session(store, sid, crew="crew-a", hours_ago=2, g=9.81):
    assert store.insert_session(sid, MASS, g, crew, T - timedelta(hours=hours_ago))


def rep(ing, sid, n, src, work=None, rom=None, seq=None, g=9.81, node=None, hours_ago=1.5):
    ing.clock = lambda: T - timedelta(hours=hours_ago) + timedelta(seconds=n)
    seq = seq if seq is not None else n + (1000 if src == "load_cell" else 0) + ord(sid[0]) * 10
    m = {
        "v": 1, "node": node or ("camera" if src == "camera" else "exercise-1"), "boot": 7,
        "seq": seq, "age_ms": 0, "type": "rep", "session": sid, "rep": n, "src": src,
        "peak_n": 120.0, "work_j": work if src == "camera" else None,
        "rom_m": rom if src == "camera" else None, "g": g, "mass_kg": MASS, "t0_ms": 1000,
        "t1_ms": 1400,
    }  # fmt: skip
    res = ing.ingest_rep(m, channel="http")
    assert res.reason is None, res.reason


def test_exercise_day_sums_and_null(rig):
    store, ing = rig
    session(store, "A")
    rep(ing, "A", 1, "camera", 38.6, 0.379)
    rep(ing, "A", 2, "camera", 40.0, 0.390)
    rep(ing, "A", 1, "load_cell")
    rep(ing, "A", 2, "load_cell")
    session(store, "B", hours_ago=1)
    rep(ing, "B", 1, "camera", 41.4, 0.4)
    d = exercise_day(store, "crew-a", T)
    assert (d["sessions"], d["camera_reps"], d["excluded_reps"], d["replay"]) == (2, 3, 0, False)
    assert d["camera_work_j"] == pytest.approx(120.0)
    assert d["cell_work_j"] == pytest.approx(76.9)
    empty = exercise_day(store, "crew-b", T)
    assert (empty["sessions"], empty["camera_work_j"], empty["cell_work_j"]) == (0, None, None)


def test_resend_later_seq_wins(rig):
    store, ing = rig
    session(store, "A")
    rep(ing, "A", 1, "camera", 38.6, 0.379, seq=1)
    rep(ing, "A", 2, "camera", 40.0, 0.39, seq=5)
    rep(ing, "A", 2, "camera", 41.0, 0.39, seq=9)
    d = exercise_day(store, "crew-a", T)
    assert d["camera_reps"] == 2 and d["camera_work_j"] == pytest.approx(79.6)


def test_other_gravity_excluded(rig):
    store, ing = rig
    session(store, "A")
    rep(ing, "A", 1, "camera", 38.6, 0.379)
    rep(ing, "A", 2, "camera", 40.0, 0.39)
    rep(ing, "A", 3, "camera", 6.5, 0.4, g=1.62)
    d = exercise_day(store, "crew-a", T)
    assert d["camera_work_j"] == pytest.approx(78.6)
    assert (d["camera_reps"], d["excluded_reps"]) == (2, 1)


def test_crew_scope(rig):
    store, ing = rig
    session(store, "N", crew=None)
    rep(ing, "N", 1, "camera", 30.0, 0.3)
    assert exercise_day(store, "crew-a", T)["camera_reps"] == 0
    assert exercise_day(store, None, T)["camera_reps"] == 1


def test_replay_without_session_row(rig):
    store, ing = rig
    rep(ing, "s9", 1, "camera", 30.0, 0.3, node="sim-1")
    d = exercise_day(store, None, T)
    assert d["replay"] is True and d["camera_reps"] == 1 and d["sessions"] == 0


def test_window_uses_rep_time(rig):
    store, ing = rig
    session(store, "A", hours_ago=1)
    rep(ing, "A", 1, "camera", 38.6, 0.379, hours_ago=25)
    rep(ing, "A", 2, "camera", 40.0, 0.39)
    d = exercise_day(store, "crew-a", T)
    assert d["camera_reps"] == 1 and d["camera_work_j"] == pytest.approx(40.0)


def test_route_and_no_conversion(settings, clock, tmp_path):
    clock.set(T)
    app = create_app(settings, clock=clock)
    app.state.ctx = SimpleNamespace(store=app.state.store, assessor=None, settings=settings)
    app.include_router(router)
    with TestClient(app) as c:
        r = c.get("/api/exercise/day?crew=crew-a")
        assert r.status_code == 200 and r.json()["camera_work_j"] is None
        assert c.get("/api/exercise/day?crew=zz").status_code == 422
    assert not any(k in r.text.lower() for k in ("kcal", "calorie"))
