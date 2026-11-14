"""Deterministic synthetic session (demo input, not measurements)."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from hub.sim import ReplayLine


def _msg(node: str, ind: str, val: float, unit: str, dev: str, seq: int, crew: str | None) -> dict:
    m = {
        "v": 1, "node": node, "boot": 1, "seq": seq, "age_ms": 0, "ind": ind, "val": val,
        "unit": unit, "src": "hobby", "dev": dev, "q": ["ok"],
    }  # fmt: skip
    if crew:
        m["crew"] = crew
    return m


def synth(minutes: int, period_s: int) -> list[ReplayLine]:
    cycles = minutes * 60 // period_s
    half = max(cycles // 2, 2)
    out: list[ReplayLine] = []
    seq = 0
    for i in range(cycles):
        t_ms = i * period_s * 1000
        t_s = i * period_s
        temp = 22.0 + 4.0 * i / max(cycles - 1, 1)
        co2 = 800.0 + 5700.0 * i / (half - 1) if i < half else 6500.0
        hr = 64 + 3 * math.sin(2 * math.pi * t_s / 60)
        rows = [
            ("cabin-1", "cabin_temp", round(temp, 2), "C", "BME280", None),
            ("cabin-1", "cabin_rh", 45, "%", "BME280", None),
            ("cabin-1", "cabin_p", 1013.0, "hPa", "BME280", None),
            ("cabin-1", "cabin_co2", round(co2, 1), "ppm", "SCD41", None),
            ("cabin-1", "cabin_lux", 400, "lx", "BH1750", None),
            ("vitals-1", "hr", round(hr, 1), "bpm", "MAX30102", "crew-a"),
            ("vitals-1", "skin_temp", 33.5, "C", "DS18B20", "crew-a"),
        ]
        for node, ind, val, unit, dev, crew in rows:
            seq += 1
            out.append(ReplayLine(t_ms, "reading", _msg(node, ind, val, unit, dev, seq, crew)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a synthetic replay file.")
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--period-s", type=int, default=5)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    lines = synth(a.minutes, a.period_s)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps({"t_ms": ln.t_ms, "kind": ln.kind, "msg": ln.msg}) + "\n")
    print(f"wrote {len(lines)} lines to {a.out}")


if __name__ == "__main__":
    main()
