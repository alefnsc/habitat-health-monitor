import json
import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
import serial
from fastapi.testclient import TestClient

import hub.serial_rig as sr
from hub.api import create_app
from hub.contract import parse_reading
from hub.ingest import Ingestor
from hub.mqtt import NodeRegistry
from hub.serial_rig import RigLink, handle_line, new_stats, open_port
from hub.store import Store
from hub.tests.helpers import msg


def line(seq=1, val=98.4, **kw) -> bytes:
    m = msg(
        node="exercise-1", boot=1, seq=seq, ind="load_raw", unit="N", val=val, dev="HX711", **kw
    )
    return json.dumps(m).encode() + b"\n"


@pytest.fixture
def ing(tmp_path, clock):
    return Ingestor(Store(tmp_path / "s.db"), clock)


def test_valid_line(ing):
    st = new_stats()
    res = handle_line(ing, line(), st)
    assert res.stored.measured_at == "2026-11-14T12:00:00.000Z"
    assert ing.store.count("outbox") == 0 and st["stored"] == 1


def test_reset_garbage_dropped(ing):
    st = new_stats()
    for ln in (b"\x00\xffreset\n", b'{"v":1,"no\n', line()):
        handle_line(ing, ln, st)
    assert (st["rejected"], st["stored"]) == (2, 1)


def test_stats_count_duplicates_and_clashes(ing, clock):
    st = new_stats()
    handle_line(ing, line(seq=1), st)
    handle_line(ing, line(seq=1), st)  # the same line again
    clock.advance(600)
    handle_line(ing, line(seq=1, val=50.0), st)  # a repeated boot number, a different sample
    assert (st["stored"], st["duplicates"], st["clashes"], st["rejected"]) == (2, 1, 1, 0)


def test_comment_line(ing):
    st = new_stats()
    assert handle_line(ing, b"# cal offset=8423\n", st) is None
    assert (st["comments"], st["rejected"]) == (1, 0)


def test_ack_line(ing, caplog):
    st = new_stats()
    ok = json.dumps({"v": 1, "type": "ack", "cmd": "servo", "ok": True}).encode() + b"\n"
    bad = json.dumps({"v": 1, "type": "ack", "cmd": "servo", "ok": False, "err": "unknown"})
    with caplog.at_level(logging.INFO):
        assert handle_line(ing, ok, st) is None
        assert "rig ack servo ok=True" in caplog.text
        handle_line(ing, bad.encode() + b"\n", st)
    assert st["acks"] == 2 and st["rejected"] == 0
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_wrong_node_and_too_long(ing):
    st = new_stats()
    bad = json.dumps(msg(node="vitals-1", ind="load_raw", unit="N", dev="HX711")).encode()
    assert handle_line(ing, bad + b"\n", st).reason == "topic_node_mismatch"
    assert handle_line(ing, b"{" + b"x" * 300 + b"}\n", st).reason == "too_large"


def test_loop_port_stream(ing, settings, monkeypatch):
    port = open_port("loop://", 100_000_000)  # loop:// emulates baud timing
    monkeypatch.setattr(sr, "open_port", lambda url, baud: port)
    nodes = NodeRegistry(ing.clock)
    link = RigLink(replace(settings, serial_port="loop://"), ing, nodes)
    t = time.perf_counter()
    link.start()
    feeder = threading.Thread(
        target=lambda: [port.write(line(seq=i + 1)) for i in range(800)] and port.write(line(seq=1))
    )
    feeder.start()  # the loop:// queue is bounded, so it is fed while RigLink reads
    while link.stats()["lines"] < 801 and time.perf_counter() - t < 5:
        time.sleep(0.01)
    link.stop()
    assert link.stats()["stored"] == 800 and time.perf_counter() - t < 2
    assert link.stats()["duplicates"] == 1  # the 801st line repeats the first one
    by_node = {n.node: n for n in nodes.snapshot()}
    assert (by_node["exercise-1"].duplicates, by_node["exercise-1"].clashes) == (1, 0)


class FlakyPort:
    def __init__(self, fail_on):
        self.fail_on, self.n = fail_on, 0

    def readline(self):
        self.n += 1
        if self.n == self.fail_on:
            raise serial.SerialException("unplugged")
        if self.n > 6:
            time.sleep(0.05)
            return b""
        return line(seq=self.n)

    def close(self):
        pass

    def cancel_read(self):
        pass


def test_reconnect(ing, settings, clock, monkeypatch):
    monkeypatch.setattr(sr, "RECONNECT_S", 0.05)
    ports = [FlakyPort(3), FlakyPort(0)]
    opened = []

    def fake(url, baud):
        p = ports[len(opened)] if len(opened) < len(ports) else FlakyPort(0)
        opened.append(p)
        return p

    monkeypatch.setattr(sr, "open_port", fake)
    nodes = NodeRegistry(clock)
    seen = []
    nodes.on_change(lambda: seen.append([n.online for n in nodes.snapshot()]))
    link = RigLink(replace(settings, serial_port="x"), ing, nodes)
    link.start()
    deadline = time.time() + 3
    while time.time() < deadline and link.stats()["reconnects"] < 1:
        time.sleep(0.02)
    time.sleep(0.2)
    link.stop()
    assert link.stats()["reconnects"] == 1 and link.stats()["stored"] > 2
    # D40: exercise-1 and cabin-1 share the cable, so both flip together
    assert [True, True] in seen and [False, False] in seen and seen[-1] == [True, True]


def test_disabled_without_port(settings, clock):
    before = threading.active_count()
    with TestClient(create_app(replace(settings, serial_port=None), clock=clock)) as c:
        assert c.get("/api/status").status_code == 200
        assert c.app.state.rig is None
    assert threading.active_count() <= before + 1


D40_SERIAL_READINGS = {
    ("cabin-1", "cabin_temp"),  # DHT11, always built (D40)
    ("cabin-1", "cabin_rh"),
    ("exercise-1", "load_raw"),  # only with ENABLE_HX711=1
}


def check_capture(lines: list[str]) -> set[tuple[str, str]]:
    """Every reading line of a UNO capture parses under contract v1 as a D40 serial reading."""
    seen = set()
    for raw in lines:
        if raw.startswith("{") and '"type"' not in raw:  # skip acks, `#` comments and blanks
            r = parse_reading(raw, max_bytes=256)
            assert (r.node, r.ind) in D40_SERIAL_READINGS, raw
            seen.add((r.node, r.ind))
    assert {("cabin-1", "cabin_temp"), ("cabin-1", "cabin_rh")} <= seen  # the D40 default build
    return seen


def test_capture_check_on_d40_lines():
    # Lines in the exact shape of exercise-uno.ino buildReading()/buildAck() with the D40 defaults.
    lines = [
        "# exercise-1 boot=8",
        (
            '{"v":1,"node":"cabin-1","boot":8,"seq":601,"age_ms":0,"ind":"cabin_temp","val":25.2,'
            '"unit":"C","src":"hobby","dev":"DHT11","q":["ok"]}'
        ),
        (
            '{"v":1,"node":"cabin-1","boot":8,"seq":602,"age_ms":0,"ind":"cabin_rh","val":52,'
            '"unit":"%","src":"hobby","dev":"DHT11","q":["ok"]}'
        ),
        '{"v":1,"node":"exercise-1","type":"ack","cmd":"alarm","ok":true}',
    ]
    assert check_capture(lines) == {("cabin-1", "cabin_temp"), ("cabin-1", "cabin_rh")}
    with pytest.raises(AssertionError):
        check_capture(lines[:1] + lines[3:])  # no DHT11 lines: not a D40 capture


def test_capture_contract():
    p = Path(__file__).parent / "fixtures" / "rig_capture.jsonl"
    if not p.exists():
        pytest.skip("no real UNO capture yet: save a minute of its serial output to " + str(p))
    check_capture(p.read_text().splitlines())


def test_cabin_line_accepted_and_tilt_rejected_over_serial(ing):
    # D40: the UNO also reads the DHT11, so cabin-1 lines share the serial link
    st = new_stats()
    cab = msg(node="cabin-1", boot=1, seq=1, ind="cabin_temp", unit="C", val=23.0, dev="DHT11")
    assert handle_line(ing, json.dumps(cab).encode() + b"\n", st).reason is None
    tilt = msg(node="tilt-1", boot=1, seq=2, ind="tilt", unit="state", val=1, dev="KY017")
    res = handle_line(ing, json.dumps(tilt).encode() + b"\n", st)
    assert res.reason == "topic_node_mismatch"


def test_serial_nodes_go_online_and_offline_together(ing, settings, clock):
    reg = NodeRegistry(clock)
    link = RigLink(settings, ing, nodes=reg)
    link._set_online(True)
    assert {s.node for s in reg.snapshot() if s.online} == {"exercise-1", "cabin-1"}
    link._set_online(False)
    assert not any(s.online for s in reg.snapshot())
