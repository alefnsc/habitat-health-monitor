"""Second, public destination for crossed-link items: consent filter, batching, HMAC (D38)."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx
from receiver.signing import HEADER, sign

from .consent import is_public
from .engine import OutboxItem


class PublicUplink:
    def __init__(
        self,
        client: httpx.Client,
        secret: str,
        public_crews: frozenset[str],
        public_reps: bool = False,
        flush_s: float = 10.0,
        max_queue: int = 5000,
        batch: int = 500,
    ) -> None:
        self.client, self.secret = client, secret
        self.public_crews, self.public_reps = public_crews, public_reps
        self.flush_s, self.max_queue, self.batch = flush_s, max_queue, batch
        self.queue: list[OutboxItem] = []
        self.beacon: Any = None
        self.offered_id = 0
        self.delivered_id = 0
        self.filtered = self.overflow = self.failures = 0
        self._last_flush = -math.inf

    def offer(self, items: list[OutboxItem], beacon: Any) -> None:
        for it in items:
            if it.id <= self.offered_id:
                continue
            self.offered_id = it.id
            if is_public(it, self.public_crews, self.public_reps):
                self.queue.append(it)
            else:
                self.filtered += 1
        extra = len(self.queue) - self.max_queue
        if extra > 0:
            del self.queue[:extra]
            self.overflow += extra
        if beacon is not None:
            self.beacon = beacon

    def flush(self, now_s: float) -> bool:
        if now_s - self._last_flush < self.flush_s:
            return False
        if not self.queue and self.beacon is None:
            return False
        self._last_flush = now_s
        chunk = self.queue[: self.batch]
        doc = {
            "beacon": None if self.beacon is None else self.beacon.to_dict(),
            "items": [
                {"id": i.id, "kind": i.kind, "created_at": i.created_at, "payload": i.payload}
                for i in chunk
            ],
        }
        body = json.dumps(doc, separators=(",", ":")).encode()
        headers = {"content-type": "application/json", HEADER: sign(body, self.secret)}
        try:
            res = self.client.post("/ground/ingest", content=body, headers=headers)
            res.raise_for_status()
        except httpx.HTTPError:
            self.failures += 1
            return False
        del self.queue[: len(chunk)]
        self.beacon = None
        if chunk:
            self.delivered_id = chunk[-1].id
        return True
