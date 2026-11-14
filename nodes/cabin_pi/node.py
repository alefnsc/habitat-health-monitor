"""Cabin node logic: sensor scheduling, quality flags, contract-v1 line formatting, boot counter.

Hobby-sensor values are estimates. Flags (team values, not datasheet values except the ranges):
- settling: SCD41 for the first 60 s after measurement starts; BME280 for the first reading.
- out_of_range: outside the sensor's specified range (SCD41 above 5000 ppm).
- no_contact: a sensor that worked has failed 3 reads in a row; the value sent is 0 and must be ignored.
"""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .bme280 import Bme280, BmeError
from .scd41 import Scd41, ScdError

NODE = "cabin-1"
CYCLE_S = 5.0
PRESSURE_PERIOD_S = 60.0
SCD_SETTLE_S = 60.0
FAILS_FOR_NO_CONTACT = 3
RING = 32
UNITS = {
    "cabin_temp": "C",
    "cabin_rh": "%",
    "cabin_p": "hPa",
    "cabin_co2": "ppm",
}
DECIMALS = {"cabin_temp": 1, "cabin_rh": 1, "cabin_p": 1, "cabin_co2": 0}
FLAG_ORDER = ("motion", "no_contact", "settling", "leads_off", "out_of_range")


@dataclass(frozen=True)
class Sample:
    ind: str
    val: float
    dev: str
    q: tuple[str, ...]  # empty means ok
    t: float  # monotonic time at sampling


def format_reading(s: Sample, boot: int, seq: int, now: float) -> str:
    """One contract-v1 message as compact JSON. age_ms = now - s.t."""
    val = round(s.val, DECIMALS[s.ind])
    q = [f for f in FLAG_ORDER if f in s.q] or ["ok"]
    msg = {
        "v": 1,
        "node": NODE,
        "boot": boot,
        "seq": seq,
        "age_ms": max(0, round((now - s.t) * 1000)),
        "ind": s.ind,
        "val": int(val) if DECIMALS[s.ind] == 0 else val,
        "unit": UNITS[s.ind],
        "src": "hobby",
        "dev": s.dev,
        "q": q,
    }
    return json.dumps(msg, separators=(",", ":"))


def next_boot(state_dir: str | os.PathLike[str]) -> int:
    """Read, increment and persist the boot counter. The first ever boot returns 1."""
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "cabin-1.boot"
    try:
        n = int(f.read_text().strip())
    except (OSError, ValueError):
        n = 0
    n += 1
    tmp = f.with_suffix(".tmp")
    tmp.write_text(f"{n}\n")
    os.replace(tmp, f)
    return n


@dataclass
class _Health:
    seen_ok: bool = False
    fails: int = 0

    def ok(self) -> None:
        self.seen_ok, self.fails = True, 0

    def fail(self) -> bool:
        """Record a failure. True when the sensor should now be reported as no_contact."""
        self.fails += 1
        return self.seen_ok and self.fails >= FAILS_FOR_NO_CONTACT


@dataclass
class Cabin:
    """One call to step(now) per second returns the samples due at that moment."""

    bme: Bme280 | None
    scd: Scd41 | None
    dht: Callable[[], tuple[float, float] | None] | None = None
    log: Callable[[str], None] = print
    _next_cycle: float = 0.0
    _next_pressure: float = 0.0
    _scd_started: float = 0.0
    _last_pressure: tuple[float, float] | None = None  # (hPa, time)
    _bme_h: _Health = field(default_factory=_Health)
    _scd_h: _Health = field(default_factory=_Health)
    _first_bme: bool = True
    _scd_pending: bool = False
    _t0: float | None = None

    def start(self, now: float) -> None:
        self._t0 = now
        self._next_cycle = now
        self._next_pressure = now
        if self.scd:
            try:
                self.scd.start()
                self._scd_started = now
            except (OSError, ScdError) as e:
                self.log(f"# scd41 start failed: {e}")
                self.scd = None
        else:
            self.log("# scd41 absent")
        if not self.bme:
            self.log("# bme280 absent")

    def step(self, now: float) -> list[Sample]:
        out: list[Sample] = []
        if now >= self._next_cycle:
            self._next_cycle += CYCLE_S
            self._scd_pending = self.scd is not None
            out += self._read_bme(now)
            out += self._read_dht(now)
        if self.scd and now >= self._next_pressure:
            self._next_pressure += PRESSURE_PERIOD_S
            self._send_pressure(now)
        if self._scd_pending and self.scd:
            out += self._read_scd(now)  # retried every second until data is ready
        return out

    def _read_bme(self, now: float) -> list[Sample]:
        if not self.bme:
            return []
        try:
            r = self.bme.read()
        except (OSError, BmeError) as e:
            self.log(f"# bme280 read failed: {e}")
            if self._bme_h.fail():
                return [Sample(i, 0.0, "BME280", ("no_contact",), now)
                        for i in ("cabin_temp", "cabin_rh", "cabin_p")]  # fmt: skip
            return []
        self._bme_h.ok()
        self._last_pressure = (r.pressure_hpa, now)
        settle = ("settling",) if self._first_bme else ()
        self._first_bme = False
        oor = (
            not -40.0 <= r.temp_c <= 85.0,
            not 0.0 <= r.rh_pct <= 100.0,
            not 300.0 <= r.pressure_hpa <= 1100.0,
        )
        return [
            Sample("cabin_temp", r.temp_c, "BME280", settle + (("out_of_range",) * oor[0]), now),
            Sample("cabin_rh", r.rh_pct, "BME280", settle + (("out_of_range",) * oor[1]), now),
            Sample("cabin_p", r.pressure_hpa, "BME280", settle + (("out_of_range",) * oor[2]), now),
        ]  # fmt: skip

    def _read_dht(self, now: float) -> list[Sample]:
        if not self.dht:
            return []
        r = self.dht()
        if r is None:
            return []
        t, rh = r
        return [Sample("cabin_temp", t, "DHT22", (), now), Sample("cabin_rh", rh, "DHT22", (), now)]

    def _send_pressure(self, now: float) -> None:
        assert self.scd
        lp = self._last_pressure
        if lp is None or now - lp[1] > PRESSURE_PERIOD_S:
            self.log("# scd41 using default pressure 101300 Pa")
            hpa = 1013.0
        else:
            hpa = lp[0]
            self.log(f"# scd41 ambient_pressure_pa={round(hpa * 100)}")
        try:
            self.scd.set_ambient_pressure(hpa)
        except (OSError, ScdError) as e:
            self.log(f"# scd41 pressure write failed: {e}")

    def _read_scd(self, now: float) -> list[Sample]:
        assert self.scd
        try:
            if not self.scd.data_ready():
                return []
            r = self.scd.read()
        except (OSError, ScdError) as e:
            self.log(f"# scd41 read failed: {e}")
            self._scd_pending = False
            if self._scd_h.fail():
                return [Sample("cabin_co2", 0.0, "SCD41", ("no_contact",), now)]
            return []
        self._scd_pending = False
        self._scd_h.ok()
        q: tuple[str, ...] = ()
        if now - self._scd_started < SCD_SETTLE_S:
            q += ("settling",)
        if r.co2_ppm > 5000:
            q += ("out_of_range",)
        return [Sample("cabin_co2", float(r.co2_ppm), "SCD41", q, now)]


class Ring:
    """Newest 32 unsent samples, drained oldest first (same size as the firmware ring)."""

    def __init__(self) -> None:
        self.q: deque[Sample] = deque(maxlen=RING)
        self.dropped = 0

    def push(self, s: Sample) -> None:
        if len(self.q) == self.q.maxlen:
            self.dropped += 1
        self.q.append(s)
