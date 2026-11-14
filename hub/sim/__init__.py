"""Simulator node sim-1: replays recorded or synthetic sessions over MQTT."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

NODE = "sim-1"
TOPIC_READING = f"habitat/v1/r/{NODE}"
TOPIC_REP = f"habitat/v1/rep/{NODE}"
TOPIC_STATUS = f"habitat/v1/status/{NODE}"


@dataclass(frozen=True)
class ReplayLine:
    t_ms: int
    kind: Literal["reading", "rep"]
    msg: dict


def load_replay(path: Path) -> list[ReplayLine]:
    lines: list[ReplayLine] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        d = json.loads(raw)
        lines.append(ReplayLine(int(d["t_ms"]), d["kind"], d["msg"]))
    return lines


def rewrite(line: ReplayLine, *, boot: int, seq: int, age_ms: int) -> tuple[str, bytes]:
    msg = dict(line.msg)
    msg.update(node=NODE, boot=boot, seq=seq, age_ms=age_ms)
    if line.kind == "reading":
        msg["src"] = "replay"
        topic = TOPIC_READING
    else:
        topic = TOPIC_REP
    return topic, json.dumps(msg, separators=(",", ":")).encode("utf-8")


def next_boot(state_path: Path) -> int:
    state_path = Path(state_path)
    try:
        boot = int(state_path.read_text().strip()) + 1
    except (FileNotFoundError, ValueError):
        boot = 1
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(str(boot))
    return boot


def replay(
    lines: list[ReplayLine],
    publish: Callable[[str, bytes], None],
    sleep: Callable[[float], None] = time.sleep,
    *,
    boot: int,
    speed: float = 1.0,
    backdate: bool = False,
    loop: bool = False,
    max_cycles: int | None = None,
) -> int:
    """Publish the lines in order; returns the number of messages published."""
    if not lines:
        return 0
    seq = 0
    cycles = 0
    span = lines[-1].t_ms - lines[0].t_ms
    gap_ms = span / (len(lines) - 1) if len(lines) > 1 else 1000
    while True:
        prev: int | None = None
        for line in lines:
            if prev is not None and not backdate and line.t_ms > prev:
                sleep((line.t_ms - prev) / 1000 / speed)
            prev = line.t_ms
            seq += 1
            age = lines[-1].t_ms - line.t_ms if backdate else 0
            topic, payload = rewrite(line, boot=boot, seq=seq, age_ms=age)
            publish(topic, payload)
        cycles += 1
        if not loop or (max_cycles is not None and cycles >= max_cycles):
            return seq
        if not backdate:
            sleep(gap_ms / 1000 / speed)
