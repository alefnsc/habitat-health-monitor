"""Builders shared by hub tests."""

from __future__ import annotations

from hub.contract import Reading, parse_reading


def msg(**kw) -> dict:
    base = {
        "v": 1, "node": "cabin-1", "boot": 2, "seq": 10, "age_ms": 0, "ind": "cabin_co2",
        "val": 812, "unit": "ppm", "src": "hobby", "dev": "SCD41", "q": ["ok"],
    }  # fmt: skip
    base.update(kw)
    return base


def reading(**kw) -> Reading:
    return parse_reading(msg(**kw))


def hr(seq: int = 1, val: float = 72, **kw) -> dict:
    return msg(node="vitals-1", boot=3, seq=seq, ind="hr", val=val, unit="bpm",
               src="hobby", dev="MAX30102", **kw)  # fmt: skip
