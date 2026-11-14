"""Record valid readings and reps from the broker, or convert a mosquitto_sub capture."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from hub.config import load_settings
from hub.contract import ContractError, parse_reading, parse_rep
from hub.sim import ReplayLine


def record_line(topic: str, payload: bytes, t_ms: int) -> ReplayLine | None:
    parts = topic.split("/")
    if len(parts) != 4 or parts[:2] != ["habitat", "v1"] or parts[2] not in ("r", "rep"):
        return None
    kind = "reading" if parts[2] == "r" else "rep"
    try:
        (parse_reading if kind == "reading" else parse_rep)(payload)
        msg = json.loads(payload.decode("utf-8"))
    except (ContractError, ValueError):
        return None
    return ReplayLine(t_ms, kind, msg)  # type: ignore[arg-type]


def convert_capture(lines: Iterable[str]) -> list[ReplayLine]:
    """`mosquitto_sub -F '%U %t %p'` lines: Unix time with decimals, topic, payload."""
    out: list[ReplayLine] = []
    t0: float | None = None
    for raw in lines:
        parts = raw.rstrip("\n").split(" ", 2)
        if len(parts) != 3:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        rec = record_line(parts[1], parts[2].encode("utf-8"), 0)
        if rec is None:
            continue
        if t0 is None:
            t0 = t
        out.append(ReplayLine(round((t - t0) * 1000), rec.kind, rec.msg))
    return out


def _write(path: Path, lines: list[ReplayLine]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps({"t_ms": ln.t_ms, "kind": ln.kind, "msg": ln.msg}) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Record sim replay files.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--from-capture", type=Path)
    a = ap.parse_args()
    if a.from_capture:
        lines = convert_capture(a.from_capture.read_text(encoding="utf-8").splitlines())
        _write(a.out, lines)
        print(f"wrote {len(lines)} lines to {a.out}")
        return

    import paho.mqtt.client as mqtt

    cfg = load_settings(os.environ)

    lines: list[ReplayLine] = []
    start = time.monotonic()
    lock = threading.Lock()

    def on_message(_c, _u, m):
        rec = record_line(m.topic, m.payload, round((time.monotonic() - start) * 1000))
        if rec:
            with lock:
                lines.append(rec)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt_user:
        client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
    client.on_message = on_message
    client.connect(cfg.mqtt_host, cfg.mqtt_port)
    client.subscribe([("habitat/v1/r/#", 1), ("habitat/v1/rep/#", 1)])
    client.loop_start()
    time.sleep(a.seconds)
    client.loop_stop()
    client.disconnect()
    with lock:
        _write(a.out, lines)
    print(f"recorded {len(lines)} lines to {a.out}")


if __name__ == "__main__":
    main()
