"""Serial reader for the exercise rig: load_raw lines, ack lines, comments (H13)."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import threading
import time

import serial

from hub.config import Settings
from hub.ingest import Ingestor, IngestResult
from hub.mqtt import NodeRegistry

log = logging.getLogger("hub.serial")

RIG_NODE = "exercise-1"
MAX_LINE = 256
RECONNECT_S = 2.0


def open_port(url: str, baud: int) -> serial.Serial:
    return serial.serial_for_url(url, baudrate=baud, timeout=1)


def new_stats() -> dict[str, int]:
    return dict.fromkeys(("lines", "stored", "rejected", "comments", "acks", "reconnects"), 0)


def handle_line(ingestor: Ingestor, line: bytes, stats: dict[str, int]) -> IngestResult | None:
    stats["lines"] += 1
    raw = line.strip(b"\r\n")
    if not raw.strip():
        return None
    if raw.startswith(b"#"):
        stats["comments"] += 1
        log.debug("rig %s", raw[:80])
        return None
    if raw.startswith(b"{") and b'"ack"' in raw:
        try:
            msg = json.loads(raw)
        except ValueError:
            msg = None
        if isinstance(msg, dict) and msg.get("type") == "ack":
            stats["acks"] += 1
            ok = bool(msg.get("ok"))
            text = f"rig ack {msg.get('cmd')} ok={ok}"
            if ok:
                log.info(text)
            else:
                log.warning("%s err=%s", text, msg.get("err"))
            return None
    res = ingestor.ingest_reading(raw, channel="serial", max_bytes=MAX_LINE, expected_node=RIG_NODE)
    if res.reason is None:
        stats["stored"] += 1
    else:
        stats["rejected"] += 1
    return res


class RigLink:
    def __init__(
        self, settings: Settings, ingestor: Ingestor, nodes: NodeRegistry | None = None
    ) -> None:
        self.settings = settings
        self.ingestor = ingestor
        self.nodes = nodes
        self._stats = new_stats()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._port: serial.Serial | None = None
        self._lock = threading.Lock()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def write(self, data: bytes) -> None:
        """Send a command line to the rig (used by the command router, H14)."""
        port = self._port
        if port is None:
            raise serial.SerialException("rig port closed")
        port.write(data)

    @property
    def connected(self) -> bool:
        return self._port is not None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="rig-serial", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        port = self._port
        if port is not None:
            with contextlib.suppress(Exception):  # not every port type supports cancel_read
                port.cancel_read()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _set_online(self, online: bool) -> None:
        if self.nodes is not None:
            self.nodes.set_online(RIG_NODE, online, self.nodes.clock())

    def _open(self) -> serial.Serial:
        assert self.settings.serial_port
        return open_port(self.settings.serial_port, self.settings.serial_baud)

    def _run(self) -> None:
        first = True
        while not self._stop.is_set():
            try:
                port = self._open()
            except (serial.SerialException, OSError) as e:
                log.warning("rig port open failed: %s", e)
                self._stop.wait(RECONNECT_S)
                continue
            self._port = port
            if not first:
                with self._lock:
                    self._stats["reconnects"] += 1
            first = False
            self._set_online(True)
            log.info("rig connected on %s", self.settings.serial_port)
            try:
                self._read(port)
            except (serial.SerialException, OSError) as e:
                log.warning("rig serial error: %s", e)
            finally:
                self._port = None
                with contextlib.suppress(Exception):
                    port.close()
            if self._stop.is_set():
                break
            self._set_online(False)
            self._stop.wait(RECONNECT_S)

    def _read(self, port: serial.Serial) -> None:
        while not self._stop.is_set():
            line = port.readline()
            if not line:
                continue
            local: dict[str, int] = new_stats()
            handle_line(self.ingestor, line, local)
            with self._lock:
                for k, v in local.items():
                    self._stats[k] += v


def main() -> None:
    ap = argparse.ArgumentParser(description="Capture rig lines to a file.")
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=250000)
    ap.add_argument("--capture", required=True)
    ap.add_argument("--lines", type=int, default=800)
    a = ap.parse_args()
    port = open_port(a.port, a.baud)
    n = 0
    t0 = time.monotonic()
    with open(a.capture, "wb") as f:
        while n < a.lines:
            line = port.readline()
            if line:
                f.write(line if line.endswith(b"\n") else line + b"\n")
                n += 1
    dt = time.monotonic() - t0
    print(f"{n} lines in {dt:.1f} s = {n / dt:.1f} lines/s")


if __name__ == "__main__":
    main()
