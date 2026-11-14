import json

from hub.contract import parse_reading
from hub.sim import ReplayLine, next_boot, replay, rewrite
from hub.sim.record import convert_capture, record_line
from hub.sim.synth import synth
from hub.tests.helpers import msg

REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


def test_rewrite_reading():
    topic, payload = rewrite(ReplayLine(0, "reading", msg()), boot=7, seq=1, age_ms=0)
    assert topic == "habitat/v1/r/sim-1"
    r = parse_reading(payload, max_bytes=256)
    assert (r.node, r.boot, r.seq, r.src) == ("sim-1", 7, 1, "replay")
    assert (r.ind, r.val, r.unit, r.dev, r.q) == ("cabin_co2", 812.0, "ppm", "SCD41", ("ok",))


def test_rewrite_intake():
    m = msg(node="food", ind="intake_sodium_mg", val=2400, unit="mg", src="self", dev="catalog",
            crew="crew-b")  # fmt: skip
    _, payload = rewrite(ReplayLine(0, "reading", m), boot=3, seq=5, age_ms=0)
    r = parse_reading(payload)
    assert (r.node, r.src, r.dev, r.crew, r.val) == ("sim-1", "replay", "catalog", "crew-b", 2400.0)


def test_rewrite_rep_keeps_src():
    topic, payload = rewrite(ReplayLine(0, "rep", REP), boot=1, seq=1, age_ms=0)
    d = json.loads(payload)
    assert topic == "habitat/v1/rep/sim-1" and d["node"] == "sim-1" and d["src"] == "camera"


def lines3():
    return [ReplayLine(t, "reading", msg()) for t in (0, 1000, 2000)]


def run(**kw):
    pubs, sleeps = [], []
    replay(lines3(), lambda t, p: pubs.append((t, json.loads(p))), sleeps.append, boot=1, **kw)
    return pubs, sleeps


def test_timing_speed():
    pubs, sleeps = run(speed=10)
    assert sleeps == [0.1, 0.1] and len(pubs) == 3
    assert [p["seq"] for _, p in pubs] == [1, 2, 3]


def test_backdate():
    pubs, sleeps = run(backdate=True)
    assert sleeps == [] and [p["age_ms"] for _, p in pubs] == [2000, 1000, 0]


def test_loop():
    pubs, _ = run(loop=True, max_cycles=2)
    assert [p["seq"] for _, p in pubs] == [1, 2, 3, 4, 5, 6]


def test_next_boot(tmp_path):
    p = tmp_path / ".state" / "sim-1.boot"
    assert next_boot(p) == 1 and p.read_text() == "1"
    assert next_boot(p) == 2


def test_synth_profile():
    lines = synth(60, 5)
    assert len(lines) == 5040
    co2 = [ln.msg["val"] for ln in lines if ln.msg["ind"] == "cabin_co2"]
    temp = [ln.msg["val"] for ln in lines if ln.msg["ind"] == "cabin_temp"]
    assert co2[0] == 800 and co2[-1] == 6500
    assert 5000 < sum(co2) / len(co2) < 5200
    assert temp[0] == 22.0 and temp[-1] == 26.0
    for i, ln in enumerate(lines):
        _, payload = rewrite(ln, boot=1, seq=i + 1, age_ms=0)
        parse_reading(payload, max_bytes=256)


def test_record_line():
    raw = json.dumps(msg()).encode()
    r = record_line("habitat/v1/r/cabin-1", raw, 1500)
    assert r == ReplayLine(1500, "reading", msg())
    assert record_line("habitat/v1/status/cabin-1", b"online", 0) is None
    assert record_line("habitat/v1/r/cabin-1", b'{"v":1}', 0) is None


def test_convert_capture():
    a = json.dumps(msg())
    b = json.dumps(msg(seq=11))
    out = convert_capture(
        [
            f"1763121599.000 habitat/v1/badge/cabin-1 {a}",
            f"1763121600.250 habitat/v1/r/cabin-1 {a}",
            f"1763121601.250 habitat/v1/r/cabin-1 {b}",
        ]
    )
    assert [ln.t_ms for ln in out] == [0, 1000] and len(out) == 2
