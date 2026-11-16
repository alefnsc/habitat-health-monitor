"""Hourly outdoor weather -> contract-v1 readings (D45 §4.2). Pure: no network, no clock, no files.

Node earth-1, src ref, dev WEATHER, no crew. A missing value is skipped, never filled. `seq` is
fixed per hour and indicator, so pulling the same hours twice is a harmless duplicate at the hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

NODE = "earth-1"
DEV = "WEATHER"
SRC = "ref"
BOOT = 1
K: dict[str, int] = {"earth_temp": 1, "earth_rh": 2, "earth_p": 3}
UNITS: dict[str, str] = {"earth_temp": "C", "earth_rh": "%", "earth_p": "hPa"}
RANGES: dict[str, tuple[float, float]] = {
    "earth_temp": (-90.0, 60.0), "earth_rh": (0.0, 100.0), "earth_p": (850.0, 1090.0),
}  # fmt: skip


@dataclass(frozen=True)
class HourRow:
    t: datetime  # aware, the hour the provider reports
    temp_c: float | None
    rh_pct: float | None
    p_hpa: float | None


def map_hours(rows: list[HourRow], *, now_ms: int) -> list[dict]:
    """Readings in time order; age_ms is the true age of each hour at `now_ms`."""
    out: list[tuple[int, int, dict]] = []
    for row in rows:
        t_ms = int(row.t.timestamp() * 1000)
        if t_ms > now_ms:
            continue  # a forecast hour is not a reading
        for ind, val in (
            ("earth_temp", row.temp_c),
            ("earth_rh", row.rh_pct),
            ("earth_p", row.p_hpa),
        ):
            if val is None:
                continue
            lo, hi = RANGES[ind]
            out.append((t_ms, K[ind], {
                "v": 1, "node": NODE, "boot": BOOT, "seq": t_ms // 3_600_000 * 4 + K[ind],
                "age_ms": now_ms - t_ms, "ind": ind, "val": float(val), "unit": UNITS[ind],
                "src": SRC, "dev": DEV, "q": ["ok"] if lo <= val <= hi else ["out_of_range"],
            }))  # fmt: skip
    out.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in out]
