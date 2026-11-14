"""Minimal I2C bus interface. The real one wraps smbus2 (MIT); tests use a fake."""

from __future__ import annotations

from typing import Protocol


class I2CBus(Protocol):
    def write(self, addr: int, data: bytes) -> None: ...

    def read(self, addr: int, n: int) -> bytes: ...

    def write_read(self, addr: int, data: bytes, n: int) -> bytes: ...


class SmbusI2C:
    """I2C on /dev/i2c-<bus> through smbus2 (MIT licence). Import happens here, not at module load."""

    def __init__(self, bus_number: int = 1) -> None:
        from smbus2 import SMBus

        self._bus = SMBus(bus_number)

    def write(self, addr: int, data: bytes) -> None:
        from smbus2 import i2c_msg

        self._bus.i2c_rdwr(i2c_msg.write(addr, list(data)))

    def read(self, addr: int, n: int) -> bytes:
        from smbus2 import i2c_msg

        msg = i2c_msg.read(addr, n)
        self._bus.i2c_rdwr(msg)
        return bytes(msg)

    def write_read(self, addr: int, data: bytes, n: int) -> bytes:
        from smbus2 import i2c_msg

        w, r = i2c_msg.write(addr, list(data)), i2c_msg.read(addr, n)
        self._bus.i2c_rdwr(w, r)  # repeated start, as the BME280 datasheet describes
        return bytes(r)

    def close(self) -> None:
        self._bus.close()
