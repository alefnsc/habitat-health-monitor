"""SCD41 driver (I2C 0x62): periodic measurement, CRC-8 framing, ambient pressure.

Datasheet: Sensirion SCD4x, sections 3.5 (I2C commands) and 3.11 (CRC). Commands are 16-bit words,
each data word is followed by a CRC-8 (polynomial 0x31, init 0xFF). The ambient pressure command
takes hPa. The sensor's own temperature and humidity output self-heats and is discarded.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .bus import I2CBus

ADDR = 0x62
CMD_START_PERIODIC = 0x21B1
CMD_READ_MEASUREMENT = 0xEC05
CMD_STOP_PERIODIC = 0x3F86
CMD_GET_DATA_READY = 0xE4B8
CMD_SET_AMBIENT_PRESSURE = 0xE000


class ScdError(RuntimeError):
    pass


def crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def word_frame(value: int) -> bytes:
    """A 16-bit word followed by its CRC, as sent for command arguments."""
    w = value.to_bytes(2, "big")
    return w + bytes([crc8(w)])


def parse_words(frame: bytes, count: int) -> list[int]:
    """Check the CRC of each 3-byte group and return the words."""
    if len(frame) != 3 * count:
        raise ScdError(f"expected {3 * count} bytes, got {len(frame)}")
    out = []
    for i in range(count):
        w, c = frame[3 * i : 3 * i + 2], frame[3 * i + 2]
        if crc8(w) != c:
            raise ScdError(f"CRC mismatch in word {i}")
        out.append(int.from_bytes(w, "big"))
    return out


@dataclass(frozen=True)
class ScdReading:
    co2_ppm: int


def parse_measurement(frame: bytes) -> ScdReading:
    """9 bytes: CO2, temperature, humidity words with CRC. Only CO2 is kept."""
    co2, _t, _rh = parse_words(frame, 3)
    return ScdReading(co2_ppm=co2)


def pressure_hpa_word(pressure_hpa: float) -> int:
    """Ambient pressure argument in hPa, clamped to the sensor's 700 to 1200 hPa range."""
    return round(min(max(pressure_hpa, 700.0), 1200.0))


class Scd41:
    def __init__(self, bus: I2CBus, sleep: Callable[[float], None] = time.sleep) -> None:
        self.bus, self._sleep = bus, sleep

    def _cmd(self, cmd: int, arg: int | None = None) -> None:
        data = cmd.to_bytes(2, "big") + (word_frame(arg) if arg is not None else b"")
        self.bus.write(ADDR, data)

    def start(self) -> None:
        """Stop any running measurement, wait 500 ms, start the 5 s periodic mode."""
        self._cmd(CMD_STOP_PERIODIC)
        self._sleep(0.5)
        self._cmd(CMD_START_PERIODIC)

    def set_ambient_pressure(self, pressure_hpa: float) -> None:
        self._cmd(CMD_SET_AMBIENT_PRESSURE, pressure_hpa_word(pressure_hpa))
        self._sleep(0.001)

    def data_ready(self) -> bool:
        self._cmd(CMD_GET_DATA_READY)
        self._sleep(0.001)
        (word,) = parse_words(self.bus.read(ADDR, 3), 1)
        return (word & 0x07FF) != 0

    def read(self) -> ScdReading:
        self._cmd(CMD_READ_MEASUREMENT)
        self._sleep(0.001)
        return parse_measurement(self.bus.read(ADDR, 9))
