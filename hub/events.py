"""EventBus for WebSocket frames (D3)."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("hub.events")

FRAME_TYPES: frozenset[str] = frozenset({"snapshot", "assessment", "alert", "prompt", "link"})


class EventBus:
    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self.loop = loop
        self.subscribers: set[asyncio.Queue] = set()

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def publish(self, type: str, data: dict) -> None:
        if type not in FRAME_TYPES:
            raise ValueError(f"unknown frame type {type!r}")
        if not self.subscribers or self.loop is None:
            return
        frame = {"type": type, "data": data}
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self._deliver(frame)
        else:
            try:
                self.loop.call_soon_threadsafe(self._deliver, frame)
            except RuntimeError:
                pass  # loop closed

    def _deliver(self, frame: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                self.subscribers.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(None)  # the socket handler closes with 1013
