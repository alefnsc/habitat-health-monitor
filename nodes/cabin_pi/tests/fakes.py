"""Fake I2C devices for host tests. No hardware, no smbus2."""

from __future__ import annotations

import struct

from nodes.cabin_pi.scd41 import word_frame

# Calibration constants as commonly used in BME280 examples, plus an
# arbitrary humidity set, checked against the datasheet's double-precision formula in the tests.
CAL = {"T1": 27504, "T2": 26435, "T3": -1000, "P1": 36477, "P2": -10685, "P3": 3024, "P4": 2855, "P5": 140,
           "P6": -7, "P7": 15500, "P8": -14600, "P9": 6000, "H1": 75, "H2": 362, "H3": 0, "H4": 313, "H5": 50, "H6": 30}  # fmt: skip
ADC_T, ADC_P, ADC_H = 519888, 415148, 28000


def cal_block1() -> bytes:
    c = CAL
    return struct.pack("<HhhHhhhhhhhh", c["T1"], c["T2"], c["T3"], c["P1"], c["P2"], c["P3"],
                       c["P4"], c["P5"], c["P6"], c["P7"], c["P8"], c["P9"])  # fmt: skip


def cal_block2() -> bytes:
    c = CAL
    e4, e5, e6 = c["H4"] >> 4, (c["H4"] & 0xF) | ((c["H5"] & 0xF) << 4), c["H5"] >> 4
    return (
        struct.pack("<h", c["H2"])
        + bytes([c["H3"], e4 & 0xFF, e5, e6 & 0xFF])
        + struct.pack("<b", c["H6"])
    )


def raw_data(adc_t=ADC_T, adc_p=ADC_P, adc_h=ADC_H) -> bytes:
    return bytes([adc_p >> 12, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4,
                  adc_t >> 12, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4,
                  adc_h >> 8, adc_h & 0xFF])  # fmt: skip


class FakeBus:
    """A BME280 (at bme_addr) and an SCD41 on one bus. Set .fail to make every access raise OSError."""

    def __init__(self, bme_addr: int | None = 0x76, chip_id: int = 0x60, scd: bool = True) -> None:
        self.bme_addr, self.chip_id, self.has_scd = bme_addr, chip_id, scd
        self.fail = False
        self.data = raw_data()
        self.writes: list[tuple[int, bytes]] = []
        self.scd_cmd = 0
        self.scd_ready = False
        self.scd_co2 = 612
        self.scd_corrupt = False

    def _check(self, addr: int) -> None:
        if self.fail or addr not in (self.bme_addr, 0x62 if self.has_scd else None):
            raise OSError(121, "Remote I/O error")

    def write(self, addr: int, data: bytes) -> None:
        self._check(addr)
        self.writes.append((addr, bytes(data)))
        if addr == 0x62:
            self.scd_cmd = int.from_bytes(data[:2], "big")

    def read(self, addr: int, n: int) -> bytes:
        self._check(addr)
        assert addr == 0x62
        if self.scd_cmd == 0xE4B8:
            return word_frame(0x8006 if self.scd_ready else 0x8000)
        assert self.scd_cmd == 0xEC05 and n == 9
        out = word_frame(self.scd_co2) + word_frame(0x6667) + word_frame(0x8000)
        if self.scd_corrupt:
            out = bytes([out[0] ^ 0x01]) + out[1:]
        return out

    def write_read(self, addr: int, data: bytes, n: int) -> bytes:
        self._check(addr)
        reg = data[0]
        if reg == 0xD0:
            return bytes([self.chip_id])
        if reg == 0x88:
            return cal_block1()
        if reg == 0xA1:
            return bytes([CAL["H1"]])
        if reg == 0xE1:
            return cal_block2()
        if reg == 0xF3:
            return b"\x00"
        if reg == 0xF7:
            return self.data
        raise AssertionError(f"unexpected register 0x{reg:02X}")
