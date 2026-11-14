"""Minimal key-value surface the public store needs, plus an in-memory fake for tests."""

from __future__ import annotations

import math
from typing import Protocol


class KV(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ex: int) -> None: ...
    def expire(self, key: str, seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def zadd(self, key: str, members: dict[str, float]) -> None: ...
    def zrangebyscore(
        self, key: str, lo: float | str, hi: float | str, offset: int = 0, count: int | None = None
    ) -> list[str]: ...
    def zremrangebyscore(self, key: str, lo: float | str, hi: float | str) -> None: ...


def _bound(v: float | str) -> float:
    if v == "-inf":
        return -math.inf
    if v == "+inf":
        return math.inf
    return float(v)


class MemoryKV:
    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttl: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def set(self, key: str, value: str, ex: int) -> None:
        self.strings[key] = value
        self.ttl[key] = ex

    def expire(self, key: str, seconds: int) -> None:
        self.ttl[key] = seconds

    def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.zsets.pop(key, None)

    def zadd(self, key: str, members: dict[str, float]) -> None:
        self.zsets.setdefault(key, {}).update(members)

    def zrangebyscore(self, key, lo, hi, offset=0, count=None):
        lo_f, hi_f = _bound(lo), _bound(hi)
        rows = sorted(
            (s, m) for m, s in self.zsets.get(key, {}).items() if lo_f <= s <= hi_f
        )
        out = [m for _, m in rows][offset:]
        return out if count is None else out[:count]

    def zremrangebyscore(self, key, lo, hi):
        lo_f, hi_f = _bound(lo), _bound(hi)
        z = self.zsets.get(key, {})
        for m in [m for m, s in z.items() if lo_f <= s <= hi_f]:
            del z[m]
