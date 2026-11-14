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
    bad = json.dumps(msg(ind="load_raw", unit="N", dev="HX711")).encode()
    assert handle_line(ing, bad + b"\n", st).reason == "topic_node_mismatch"
    assert handle_line(ing, b"{" + b"x" * 300 + b"}\n", st).reason == "too_large"


def test_loop_port_stream(ing, settings, monkeypatch):
    port = open_port("loop://", 250000)
    monkeypatch.setattr(sr, "open_port", lambda url, baud: port)
    link = RigLink(replace(settings, serial_port="loop://"), ing)
    for i in range(800):
        port.write(line(seq=i + 1))
    t = time.perf_counter()
    link.start()
    while link.stats()["lines"] < 800 and time.perf_counter() - t < 5:
        time.sleep(0.01)
    link.stop()
    assert link.stats()["stored"] == 800 and time.perf_counter() - t < 2


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
    assert [True] in seen and [False] in seen and seen[-1] == [True]


def test_disabled_without_port(settings, clock):
    before = threading.active_count()
    with TestClient(create_app(replace(settings, serial_port=None), clock=clock)) as c:
        assert c.get("/api/status").status_code == 200
        assert c.app.state.rig is None
    assert threading.active_count() <= before + 1


def test_capture_contract():
    p = Path(__file__).parent / "fixtures" / "rig_capture.jsonl"
    if not p.exists():
        pytest.skip("no rig capture yet")
    for raw in p.read_text().splitlines():
        if raw.startswith("{") and '"type"' not in raw:
            r = parse_reading(raw, max_bytes=256)
            assert (r.node, r.ind) == ("exercise-1", "load_raw")
