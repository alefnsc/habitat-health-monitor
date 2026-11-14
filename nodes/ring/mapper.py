"""Raw ring pull record -> contract-v1 readings (D41 §4). Pure: no network, no clock, no files.

A pull record is one JSON object:
  {"kind": "ring_pull", "v": 1, "pulled_at": ISO-8601, "window": {...},
   "heartrate": [rows], "daily_spo2": [docs], "sleep": [docs]}
with the vendor's v2 field names inside the three lists (see DATA_SOURCES.md, wearable ring).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

NODE = "ring-1"
DEV = "RING"
CREW = "crew-b"
BOOT: dict[str, int] = {"pull": 1, "replay": 2}
SRC: dict[str, str] = {"pull": "hobby", "replay": "replay"}
K: dict[str, int] = {"hr": 1, "spo2": 2, "sleep_h": 3}
UNITS: dict[str, str] = {"hr": "bpm", "spo2": "%", "sleep_h": "h"}
RANGES: dict[str, tuple[float, float]] = {"hr": (20, 250), "spo2": (50, 100), "sleep_h": (0, 24)}
HR_SOURCES = frozenset({"rest", "sleep"})  # the hub's HR bands are resting bands
MAIN_SLEEP = "long_sleep"

Mode = Literal["pull", "replay"]


@dataclass
class MapResult:
    readings: list[dict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _reading(ind: str, val: float, t_ms: int, ref_ms: int, mode: Mode) -> dict:
    lo, hi = RANGES[ind]
    return {
        "v": 1, "node": NODE, "boot": BOOT[mode], "seq": t_ms // 1000 * 4 + K[ind],
        "age_ms": max(0, ref_ms - t_ms), "ind": ind, "val": val, "unit": UNITS[ind],
        "src": SRC[mode], "dev": DEV, "q": ["ok"] if lo <= val <= hi else ["out_of_range"],
        "crew": CREW,
    }  # fmt: skip


def map_pull(record: dict, *, mode: Mode, now_ms: int | None = None) -> MapResult:
    """Map one pull record. A pull's age is `now_ms - sample`; a replay's is `pulled_at - sample`."""
    if mode not in BOOT:
        raise ValueError(f"unknown mode {mode!r}")
    if mode == "pull":
        if now_ms is None:
            raise ValueError("a pull needs now_ms")
        ref_ms = now_ms
    else:
        ref_ms = _ms(record["pulled_at"])
    skipped: Counter[str] = Counter()
    out: list[tuple[int, int, dict]] = []

    def emit(ind: str, val: float, t_ms: int) -> None:
        out.append((t_ms, K[ind], _reading(ind, val, t_ms, ref_ms, mode)))

    for row in record.get("heartrate") or []:
        source = row.get("source")
        if source not in HR_SOURCES:
            skipped[f"hr_source_{source}"] += 1
            continue
        t_ms = row.get("timestamp_unix")
        emit("hr", float(row["bpm"]), int(t_ms) if t_ms is not None else _ms(row["timestamp"]))

    night_end: dict[str, int] = {}
    for doc in record.get("sleep") or []:
        if doc.get("type") != MAIN_SLEEP:
            skipped[f"sleep_type_{doc.get('type')}"] += 1
            continue
        total_s = doc.get("total_sleep_duration")
        end_ms = _ms(doc["bedtime_end"])
        night_end[doc["day"]] = max(end_ms, night_end.get(doc["day"], end_ms))
        if total_s is None:
            skipped["sleep_no_duration"] += 1
            continue
        emit("sleep_h", round(total_s / 3600, 2), end_ms)

    for doc in record.get("daily_spo2") or []:
        avg = (doc.get("spo2_percentage") or {}).get("average")
        if avg is None:
            skipped["spo2_no_value"] += 1
        elif doc.get("day") not in night_end:
            skipped["spo2_no_night"] += 1
        else:
            emit("spo2", round(float(avg), 1), night_end[doc["day"]])

    out.sort(key=lambda x: (x[0], x[1]))
    return MapResult([r for _, _, r in out], dict(skipped))
