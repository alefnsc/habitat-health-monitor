"""Second, public destination for crossed-link items: consent filter, batching, HMAC (D38)."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx
from receiver.signing import HEADER, sign

from .consent import is_public
from .engine import OutboxItem

MAX_BACKOFF = 6


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
        self.filtered = self.overflow = self.failures = self.rejected = 0
        self._backoff = 0
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

    def _interval(self) -> float:
        if not self._backoff:
            return self.flush_s
        return min(60.0, max(1.0, self.flush_s) * 2 ** min(self._backoff, MAX_BACKOFF))

    def flush(self, now_s: float) -> bool:
        """Send one batch. Never raises: any error counts as a failure and backs off."""
        try:
            return self._flush(now_s)
        except Exception as exc:  # noqa: BLE001 - public must never break the local link
            self.failures += 1
            self._backoff = min(self._backoff + 1, MAX_BACKOFF)
            print(f"public uplink flush failed: {type(exc).__name__}", flush=True)
            return False

    def _flush(self, now_s: float) -> bool:
        if now_s - self._last_flush < self._interval():
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
        except httpx.HTTPError:
            self.failures += 1
            self._backoff = min(self._backoff + 1, MAX_BACKOFF)
            return False
        code = res.status_code
        if 400 <= code < 500 and code not in (408, 429):
            del self.queue[: len(chunk)]
            self.beacon = None
            self.rejected += 1
            print(f"public uplink rejected {code}: dropped {len(chunk)} items", flush=True)
            return False
        if not 200 <= code < 300:
            self.failures += 1
            self._backoff = min(self._backoff + 1, MAX_BACKOFF)
            return False
        del self.queue[: len(chunk)]
        self.beacon = None
        self._backoff = 0
        if chunk:
            self.delivered_id = chunk[-1].id
        return True
