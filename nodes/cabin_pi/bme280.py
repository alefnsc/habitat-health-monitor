"""BME280 driver: chip-id check, forced-mode reads, Bosch datasheet integer compensation.

Datasheet: Bosch Sensortec BME280, section 4.2.3 (integer compensation formulas) and 5.4 (registers).
Supply 3.3 V only. The BMP280 (chip id 0x58) has no humidity and is refused.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

from .bus import I2CBus

CHIP_ID = 0x60
ADDRESSES = (0x76, 0x77)
REG_ID, REG_RESET, REG_CTRL_HUM, REG_STATUS, REG_CTRL_MEAS, REG_DATA = (
    0xD0, 0xE0, 0xF2, 0xF3, 0xF4, 0xF7,
)  # fmt: skip


class BmeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Calib:
    T1: int
    T2: int
    T3: int
    P1: int
    P2: int
    P3: int
    P4: int
    P5: int
    P6: int
    P7: int
    P8: int
    P9: int
    H1: int
    H2: int
    H3: int
    H4: int
    H5: int
    H6: int


def parse_calibration(block1: bytes, h1: int, block2: bytes) -> Calib:
    """block1 = registers 0x88..0x9F (24 bytes), h1 = register 0xA1, block2 = 0xE1..0xE7 (7 bytes)."""
    if len(block1) != 24 or len(block2) != 7:
        raise BmeError("short calibration block")
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = struct.unpack("<HhhHhhhhhhhh", block1)
    h2 = struct.unpack("<h", block2[0:2])[0]
    h3 = block2[2]
    h4 = (block2[3] << 4) | (block2[4] & 0x0F)
    h5 = (block2[5] << 4) | (block2[4] >> 4)
    h4 = h4 - 4096 if h4 > 2047 else h4
    h5 = h5 - 4096 if h5 > 2047 else h5
    h6 = struct.unpack("<b", block2[6:7])[0]
    return Calib(t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9, h1, h2, h3, h4, h5, h6)


def _cdiv(a: int, b: int) -> int:
    """C-style integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def compensate_temperature(adc_t: int, c: Calib) -> tuple[int, int]:
    """Returns (t_fine, temperature in 0.01 degC)."""
    var1 = (((adc_t >> 3) - (c.T1 << 1)) * c.T2) >> 11
    d = (adc_t >> 4) - c.T1
    var2 = (((d * d) >> 12) * c.T3) >> 14
    t_fine = var1 + var2
    return t_fine, (t_fine * 5 + 128) >> 8


def compensate_pressure(adc_p: int, t_fine: int, c: Calib) -> int:
    """Returns pressure in Pa as Q24.8 (divide by 256). 0 on the degenerate P1 = 0 case."""
    var1 = t_fine - 128000
    var2 = var1 * var1 * c.P6
    var2 += (var1 * c.P5) << 17
    var2 += c.P4 << 35
    var1 = ((var1 * var1 * c.P3) >> 8) + ((var1 * c.P2) << 12)
    var1 = (((1 << 47) + var1) * c.P1) >> 33
    if var1 == 0:
        return 0
    p = 1048576 - adc_p
    p = _cdiv((((p << 31) - var2) * 3125), var1)
    var1 = (c.P9 * (p >> 13) * (p >> 13)) >> 25
    var2 = (c.P8 * p) >> 19
    return ((p + var1 + var2) >> 8) + (c.P7 << 4)


def compensate_humidity(adc_h: int, t_fine: int, c: Calib) -> int:
    """Returns relative humidity as Q22.10 (divide by 1024 for %RH)."""
    v = t_fine - 76800
    v = ((((adc_h << 14) - (c.H4 << 20) - (c.H5 * v)) + 16384) >> 15) * (
        (((((((v * c.H6) >> 10) * (((v * c.H3) >> 11) + 32768)) >> 10) + 2097152) * c.H2) + 8192)
        >> 14
    )
    v = v - (((((v >> 15) * (v >> 15)) >> 7) * c.H1) >> 4)
    v = max(0, min(v, 419430400))
    return v >> 12


@dataclass(frozen=True)
class BmeReading:
    temp_c: float
    rh_pct: float
    pressure_hpa: float


def decode_raw(data: bytes, c: Calib) -> BmeReading:
    """data = the 8 bytes from 0xF7 (press msb/lsb/xlsb, temp msb/lsb/xlsb, hum msb/lsb)."""
    if len(data) != 8:
        raise BmeError("short data block")
    adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    adc_h = (data[6] << 8) | data[7]
    if adc_t == 0x80000 or adc_p == 0x80000 or adc_h == 0x8000:
        raise BmeError("measurement skipped (reset value in the data registers)")
    t_fine, t = compensate_temperature(adc_t, c)
    return BmeReading(
        temp_c=t / 100.0,
        rh_pct=compensate_humidity(adc_h, t_fine, c) / 1024.0,
        pressure_hpa=compensate_pressure(adc_p, t_fine, c) / 256.0 / 100.0,
    )


class Bme280:
    def __init__(
        self, bus: I2CBus, addr: int, calib: Calib, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.bus, self.addr, self.calib, self._sleep = bus, addr, calib, sleep

    @classmethod
    def probe(cls, bus: I2CBus, sleep: Callable[[float], None] = time.sleep) -> Bme280:
        """Find the chip at 0x76 or 0x77, check the id is 0x60, load calibration."""
        last: Exception | None = None
        for addr in ADDRESSES:
            try:
                chip = bus.write_read(addr, bytes([REG_ID]), 1)[0]
            except OSError as e:
                last = e
                continue
            if chip != CHIP_ID:
                raise BmeError(f"chip id 0x{chip:02X} at 0x{addr:02X}, expected 0x60 (BMP280?)")
            bus.write(addr, bytes([REG_RESET, 0xB6]))
            sleep(0.01)
            b1 = bus.write_read(addr, bytes([0x88]), 24)
            h1 = bus.write_read(addr, bytes([0xA1]), 1)[0]
            b2 = bus.write_read(addr, bytes([0xE1]), 7)
            return cls(bus, addr, parse_calibration(b1, h1, b2), sleep)
        raise BmeError(f"no BME280 at 0x76 or 0x77 ({last})")

    def read(self) -> BmeReading:
        """One forced-mode measurement, oversampling x1 on all three (about 10 ms)."""
        self.bus.write(self.addr, bytes([REG_CTRL_HUM, 0x01]))
        self.bus.write(self.addr, bytes([REG_CTRL_MEAS, 0x25]))  # osrs_t x1, osrs_p x1, forced
        for _ in range(20):
            self._sleep(0.005)
            if not self.bus.write_read(self.addr, bytes([REG_STATUS]), 1)[0] & 0x08:
                break
        else:
            raise BmeError("measurement did not finish")
        return decode_raw(self.bus.write_read(self.addr, bytes([REG_DATA]), 8), self.calib)
