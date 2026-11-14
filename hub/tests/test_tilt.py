"""D39 tilt witness: pure functions, then GET /api/reps end to end."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import msg
from hub.tilt import Change, tilt_changes, tilt_witness

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def ms(n: int) -> datetime:
    return T + timedelta(milliseconds=n)


@dataclass
class Row:  # the attributes tilt_changes reads from a StoredReading
    id: int
    node: str
    val: float
    measured_at: str


def row(i, at_ms, val, node="tilt-1"):
    return Row(i, node, val, ms(at_ms).strftime("%Y-%m-%dT%H:%M:%S.") + f"{at_ms % 1000:03d}Z")


def test_changes_skip_heartbeats_and_other_nodes():
    rows = [row(1, -9000, 0), row(2, -1000, 0), row(3, 1150, 1), row(4, 1200, 1),
            row(5, 1350, 0), row(6, 1360, 1, node="vitals-1")]  # fmt: skip
    assert tilt_changes(rows) == [Change(ms(1150), 1), Change(ms(1350), 0)]


def test_first_reading_only_sets_the_state():
    assert tilt_changes([row(1, 100, 1), row(2, 200, 0)]) == [Change(ms(200), 0)]


def test_witness_around_turnaround():
    w = tilt_witness([Change(ms(1150), 1), Change(ms(1350), 0)], ms(1000), ms(1400), ms(1200))
    assert w == {"seen": True, "turn_inside": True, "offset_ms": 50,
                 "rise_at": "2026-11-14T12:00:01.150Z", "fall_at": "2026-11-14T12:00:01.350Z"}  # fmt: skip


def test_witness_late_pair_still_seen():
    w = tilt_witness([Change(ms(1500), 1), Change(ms(1700), 0)], ms(1000), ms(1400), ms(1200))
    assert w["seen"] and not w["turn_inside"] and w["offset_ms"] == 400


def test_witness_outside_window_not_seen():
    w = tilt_witness([Change(ms(2000), 1), Change(ms(2200), 0)], ms(1000), ms(1400), ms(1200))
    assert w == {"seen": False, "turn_inside": False, "offset_ms": None,
                 "rise_at": None, "fall_at": None}  # fmt: skip


def test_witness_rise_without_fall_not_seen():
    assert not tilt_witness([Change(ms(1150), 1)], ms(1000), ms(1400), ms(1200))["seen"]


def test_witness_two_pairs_nearest_midpoint_wins():
    ch = [Change(ms(600), 1), Change(ms(800), 0), Change(ms(1100), 1), Change(ms(1300), 0)]
    w = tilt_witness(ch, ms(1000), ms(1400), ms(1200))
    assert w["rise_at"] == "2026-11-14T12:00:01.100Z" and w["offset_ms"] == 0


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        yield c


def at(c, when):
    c.app.state.ingestor.clock = lambda: when


def tilt(c, when, val, seq):
    at(c, when)
    m = msg(node="tilt-1", boot=1, seq=seq, ind="tilt", unit="state", val=val, dev="KY017")
    assert c.post("/api/readings", json=m).status_code == 201


def camera_rep(seq, n, **kw):
    return {
        "v": 1, "node": "camera", "boot": 7, "seq": seq, "age_ms": 0, "type": "rep",
        "session": "s1", "rep": n, "src": "camera", "peak_n": 120.0, "work_j": 45.0,
        "rom_m": 0.5, "g": 9.81, "mass_kg": 10, "t0_ms": 1000, "t1_ms": 1400, **kw,
    }  # fmt: skip


def test_get_reps_carries_tilt_witness(client):
    assert client.post("/api/sessions", json={"session": "s1", "mass_kg": 10, "g": 9.81}).status_code == 201
    tilt(client, ms(-5000), 0, 1)  # heartbeat at rest
    tilt(client, ms(1150), 1, 2)  # rises during the lift
    tilt(client, ms(1350), 0, 3)  # falls during the lowering
    at(client, ms(1400))  # the camera anchors age_ms on t1, so t1 is at 1400 ms
    r = camera_rep(1, 1, work_ecc_j=20.0, t_con_ms=200, t_ecc_ms=200, t_turn_ms=1200)
    assert client.post("/api/reps", json=r).status_code == 201
    old = camera_rep(2, 2)  # an older camera sends no t_turn_ms
    assert client.post("/api/reps", json=old).status_code == 201
    p1, p2 = client.get("/api/reps?session=s1").json()["pairs"]
    assert p1["tilt"] == {"seen": True, "turn_inside": True, "offset_ms": 50,
                          "rise_at": "2026-11-14T12:00:01.150Z",
                          "fall_at": "2026-11-14T12:00:01.350Z"}  # fmt: skip
    assert p1["camera"]["work_ecc_j"] == 20.0 and p1["camera"]["t_turn_ms"] == 1200
    assert p2["tilt"] is None
