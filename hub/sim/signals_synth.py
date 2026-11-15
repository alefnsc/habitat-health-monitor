"""28 invented days for the signals module (D45 §9.2): demo and test input, not measurements.

python -m hub.sim.signals_synth --out data/replay/signals-synthetic-28d.jsonl

Crews crew-a and crew-c only (never crew-b, the team owner's real ring data). Replay it with
`python -m hub.sim --file data/replay/signals-synthetic-28d.jsonl --backdate --http <hub>`: the last
line lands at "now" and every reading is node sim-1, src replay. Planted effects:
- crew-a resting HR about 9 bpm above its usual range on the last 3 nights;
- cabin RH ramping 3 %/h over the last 3 hours, about 3.8 h short of the 75 % limit at the end;
- crew-c resting HR flat; crew-c SpO2 on 4 nights only (gaps);
- crew-a water logged rising, crew-a body mass slowly falling;
- one space-weather day at level 1; outdoor Earth temperature with a daily cycle the bench
  cabin follows about 2 hours later.
Camera sets are not in the file: hub.sim cannot create sessions, so lift signals show
`not enough data` on this replay (the engine tests cover them with direct sessions).
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from hub.contract import INDICATORS
from hub.sim import ReplayLine

DAYS = 28
H_MS = 3_600_000
DAY_MS = 24 * H_MS
END_MS = DAYS * DAY_MS  # the last line; nights end here, k days before it
CREWS = ("crew-a", "crew-c")
DEV = {
    "hr": "RING", "spo2": "RING", "sleep_h": "RING", "body_mass": "manual",
    "intake_water_ml": "catalog", "cabin_temp": "DHT22", "cabin_rh": "DHT22",
    "cabin_co2": "SCD41", "cabin_p": "BME280", "earth_temp": "WEATHER", "space_weather": "DONKI",
}  # fmt: skip
NOTE = {"t_ms": -1, "kind": "note", "note": "synthetic: invented data for the D45 signals demo"}


def _line(t_ms: int, ind: str, val: float, crew: str | None) -> ReplayLine:
    msg = {
        "v": 1, "node": "sim-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": ind,
        "val": round(val, 2), "unit": INDICATORS[ind], "src": "replay", "dev": DEV[ind],
        "q": ["ok"],
    }  # fmt: skip
    if crew is not None:
        msg["crew"] = crew
    return ReplayLine(int(t_ms), "reading", msg)


def earth_temp(t_ms: int) -> float:
    """A daily cycle peaking 15:00 local, where the last line is 07:00 local."""
    local_h = (7 + t_ms / H_MS) % 24
    return 18 + 6 * math.sin(2 * math.pi * (local_h - 9) / 24)


def synth(seed: int = 45) -> list[ReplayLine]:
    rnd = random.Random(seed)
    out: list[ReplayLine] = []
    for k in range(DAYS):
        night_end = END_MS - k * DAY_MS
        for crew in CREWS:
            a = crew == "crew-a"
            sleep_h = (7.0 if a else 7.5) + rnd.uniform(-0.4, 0.4)
            start = night_end - int(sleep_h * H_MS)
            base = 56 if a else 60
            rise = 9 if a and k < 3 else 0
            for t in range(start + 150_000, night_end, 300_000):  # one sample per 5 minutes
                out.append(_line(t, "hr", base + rise + rnd.uniform(-1.5, 1.5), crew))
            out.append(_line(night_end, "sleep_h", sleep_h, crew))
            if a or k in (0, 3, 9, 20):
                out.append(_line(night_end, "spo2", 97 + rnd.uniform(-0.5, 0.5), crew))
            if a or k % 3 == 0:
                lunch, dinner = night_end - 19 * H_MS, night_end - (12 - (k % 4)) * H_MS
                water = 400 + 20 * (DAYS - 1 - k) if a else 500
                out.append(_line(lunch, "intake_water_ml", 600 + rnd.uniform(-50, 50), crew))
                out.append(_line(dinner, "intake_water_ml", water + rnd.uniform(-50, 50), crew))
            if a:
                mass = 72.0 - 0.02 * (DAYS - 1 - k) + rnd.uniform(-0.1, 0.1)
                out.append(_line(night_end + 1_800_000, "body_mass", mass, crew))
        if k > 0:
            out.append(_line(night_end + 2 * H_MS, "space_weather", 1 if k == 5 else 0, None))
    for t in range(END_MS - 7 * DAY_MS, END_MS + 1, H_MS):
        out.append(_line(t, "earth_temp", earth_temp(t) + rnd.uniform(-0.2, 0.2), None))
    for t in range(END_MS - 7 * DAY_MS, END_MS + 1, 300_000):
        if t < END_MS - 2 * DAY_MS and (t // 300_000) % 6:
            continue  # every 30 minutes before the last 2 days, every 5 minutes after
        temp = 22 + 0.3 * (earth_temp(t - 2 * H_MS) - 18) + rnd.uniform(-0.1, 0.1)
        ramp_h = (t - (END_MS - 3 * H_MS)) / H_MS
        rh = 54.5 + 3 * ramp_h if ramp_h > 0 else 45 + rnd.uniform(-1, 1)
        out.append(_line(t, "cabin_temp", temp, None))
        out.append(_line(t, "cabin_rh", rh, None))
        if t >= END_MS - 2 * DAY_MS:
            out.append(_line(t, "cabin_co2", 900 + rnd.uniform(-20, 20), None))
            out.append(_line(t, "cabin_p", 1013 + rnd.uniform(-1, 1), None))
    # cabin_p before cabin_co2 at the same time: the hub derives ppCO2 from the pressure within
    # 60 s, and a CO2 sample that arrives first is flagged assumed_pressure (not assessable).
    out.sort(
        key=lambda x: (x.t_ms, x.msg["ind"] != "cabin_p", x.msg["ind"], x.msg.get("crew") or "")
    )
    return out


def write(path: Path, lines: list[ReplayLine]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        f.write(json.dumps(NOTE, separators=(",", ":")) + "\n")
        f.writelines(json.dumps({"t_ms": ln.t_ms, "kind": ln.kind, "msg": ln.msg},
                               separators=(",", ":")) + "\n" for ln in lines)  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    write(ap.parse_args().out, synth())


if __name__ == "__main__":
    main()
