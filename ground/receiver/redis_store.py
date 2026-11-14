"""Public ground store on a key-value backend: one sorted-set member per arrival (D38)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .kv import KV
from .store import Arrival, IngestResult, Summary

STATE = "g:state"
ARRIVALS = "g:arrivals"


def _empty_state() -> dict[str, Any]:
    return {
        "next_arrival_id": 1, "max_id": None, "min_id": None, "stored": 0,
        "arrivals": 0, "last_arrival_at": None, "index": [],
    }  # fmt: skip


class RedisStore:
    def __init__(
        self,
        kv: KV,
        cap_items: int = 20000,
        retention_s: int = 48 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.kv, self.cap, self.retention, self.clock = kv, cap_items, retention_s, clock

    def _load(self) -> dict[str, Any]:
        raw = self.kv.get(STATE)
        return json.loads(raw) if raw else _empty_state()

    def _save(self, st: dict[str, Any]) -> None:
        self.kv.set(STATE, json.dumps(st), ex=self.retention)
        self.kv.expire(ARRIVALS, self.retention)

    def _trim(self, st: dict[str, Any], now: float) -> None:
        idx = st["index"]
        while idx and (st["stored"] > self.cap or now - idx[0][2] > self.retention):
            aid, n, _, _ = idx.pop(0)
            self.kv.zremrangebyscore(ARRIVALS, aid, aid)
            st["stored"] -= n
            st["arrivals"] -= 1
        firsts = [e[3] for e in idx if e[3] is not None]
        st["min_id"] = firsts[0] if firsts else None

    def ingest(self, beacon: dict | None, items: list[dict], received_at: str) -> IngestResult:
        st, now = self._load(), self.clock()
        top = st["max_id"]
        new = sorted((i for i in items if top is None or i["id"] > top), key=lambda i: i["id"])
        aid = st["next_arrival_id"]
        arrival = Arrival(aid, received_at, beacon, new)
        self.kv.zadd(ARRIVALS, {json.dumps(asdict(arrival)): aid})
        st["next_arrival_id"] = aid + 1
        st["arrivals"] += 1
        st["stored"] += len(new)
        st["last_arrival_at"] = received_at
        if new:
            st["max_id"] = new[-1]["id"]
        st["index"].append([aid, len(new), now, new[0]["id"] if new else None])
        self._trim(st, now)
        self._save(st)
        return IngestResult(st["max_id"], len(new), aid)

    def arrivals_after(self, after: int, limit: int) -> list[Arrival]:
        rows = self.kv.zrangebyscore(ARRIVALS, after + 1, "+inf", offset=0, count=limit)
        return [Arrival(**json.loads(r)) for r in rows]

    def summary(self) -> Summary:
        st = self._load()
        stored, lo, hi = st["stored"], st["min_id"], st["max_id"]
        missing = 0 if stored == 0 or lo is None or hi is None else (hi - lo + 1) - stored
        return Summary(stored, lo, hi, missing, st["arrivals"], st["last_arrival_at"])

    def purge_crew(self, crew: str) -> int:
        st = self._load()
        rows = [json.loads(r) for r in self.kv.zrangebyscore(ARRIVALS, "-inf", "+inf")]
        removed = 0
        kept: dict[str, float] = {}
        counts: dict[int, tuple[int, int | None]] = {}
        for a in rows:
            before = len(a["items"])
            a["items"] = [x for x in a["items"] if x.get("payload", {}).get("crew") != crew]
            removed += before - len(a["items"])
            kept[json.dumps(a)] = a["arrival_id"]
            counts[a["arrival_id"]] = (
                len(a["items"]), a["items"][0]["id"] if a["items"] else None
            )
        self.kv.delete(ARRIVALS)
        if kept:
            self.kv.zadd(ARRIVALS, kept)
        for e in st["index"]:
            if e[0] in counts:
                e[1], e[3] = counts[e[0]]
        st["stored"] = sum(e[1] for e in st["index"])
        firsts = [e[3] for e in st["index"] if e[3] is not None]
        st["min_id"] = firsts[0] if firsts else None
        self._save(st)
        return removed
