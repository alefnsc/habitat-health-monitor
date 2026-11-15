"""MQTT subscriber, node registry and shared publisher (H8)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

import aiomqtt

from hub.config import Settings
from hub.ingest import Ingestor, IngestResult
from hub.timeutil import to_iso

log = logging.getLogger("hub.mqtt")

MAX_MQTT_BYTES = 256
BASE_SUBSCRIPTIONS = ("habitat/v1/r/+", "habitat/v1/rep/+", "habitat/v1/status/+")
BACKOFF_S = (1, 2, 4, 5)

Handler = Callable[[str, bytes], object]


@dataclass
class NodeState:
    node: str
    online: bool
    last_seen: str | None
    duplicates: int = 0  # messages that repeated a stored sample (retries), dropped
    clashes: int = 0  # readings stored under a key an earlier, different sample held

    def to_dict(self) -> dict:
        return asdict(self)


class NodeRegistry:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self.clock = clock
        self._nodes: dict[str, NodeState] = {}
        self._cbs: list[Callable[[], None]] = []

    def on_change(self, cb: Callable[[], None]) -> None:
        self._cbs.append(cb)

    def _fire(self) -> None:
        for cb in self._cbs:
            try:
                cb()
            except Exception:
                log.exception("node change callback failed")

    def seen(self, node: str, at: datetime) -> None:
        """Any message updates last_seen; a node first seen through data counts as online."""
        st = self._nodes.get(node)
        if st is None:
            self._nodes[node] = NodeState(node, True, to_iso(at))
            self._fire()
        else:
            st.last_seen = to_iso(at)

    def set_online(self, node: str, online: bool, at: datetime) -> bool:
        st = self._nodes.get(node)
        if st is None:
            self._nodes[node] = NodeState(node, online, to_iso(at))
            self._fire()
            return True
        st.last_seen = to_iso(at)
        if st.online == online:
            return False
        st.online = online
        self._fire()
        return True

    def record(self, node: str, res: IngestResult) -> None:
        """Count a duplicate or a key clash for the node that sent the message."""
        st = self._nodes.get(node)
        if st is None:
            return
        if res.duplicate:
            st.duplicates += 1
        elif res.clash:
            st.clashes += 1

    def snapshot(self) -> list[NodeState]:
        return [NodeState(**asdict(s)) for _, s in sorted(self._nodes.items())]


def route_message(
    ingestor: Ingestor,
    nodes: NodeRegistry,
    topic: str,
    payload: bytes,
    handlers: dict[str, Handler] | None = None,
) -> IngestResult | None:
    """Route one MQTT message. `handlers` maps a topic kind (e.g. `badge`) to fn(node, payload)."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "habitat" or parts[1] != "v1":
        return None
    kind, node = parts[2], parts[3]
    now = nodes.clock()
    if kind == "r":
        nodes.seen(node, now)
        res = ingestor.ingest_reading(
            payload, channel="mqtt", max_bytes=MAX_MQTT_BYTES, expected_node=node
        )
        nodes.record(node, res)
        return res
    if kind == "rep":
        nodes.seen(node, now)
        res = ingestor.ingest_rep(
            payload, channel="mqtt", max_bytes=MAX_MQTT_BYTES, expected_node=node
        )
        nodes.record(node, res)
        return res
    if kind == "status":
        text = payload.decode("utf-8", "replace").strip()
        if text in ("online", "offline"):
            nodes.set_online(node, text == "online", now)
        else:
            log.info("ignored status payload from %s: %r", node, text[:32])
        return None
    handler = (handlers or {}).get(kind)
    if handler is not None:
        nodes.seen(node, now)
        handler(node, payload)
    return None


class MqttPublisher:
    """Thread-safe publisher; messages go out over the subscriber's connection."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=1000)

    def publish(self, topic: str, payload: bytes, *, qos: int = 1, retain: bool = False) -> None:
        if self._loop is None or self._queue is None:
            log.warning("mqtt publisher not running, dropped %s", topic)
            return
        self._loop.call_soon_threadsafe(self._put, (topic, payload, qos, retain))

    def _put(self, item: tuple) -> None:
        assert self._queue is not None
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(item)

    async def _pump(self, client: aiomqtt.Client) -> None:
        assert self._queue is not None
        while True:
            topic, payload, qos, retain = await self._queue.get()
            await client.publish(topic, payload, qos=qos, retain=retain)


async def run_subscriber(
    settings: Settings,
    ingestor: Ingestor,
    nodes: NodeRegistry,
    stop: asyncio.Event,
    *,
    publisher: MqttPublisher | None = None,
    extra_subscriptions: tuple[str, ...] = (),
    handlers: dict[str, Handler] | None = None,
) -> None:
    if publisher is not None:
        publisher.attach(asyncio.get_running_loop())
    attempt = 0
    while not stop.is_set():
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_user,
                password=settings.mqtt_pass,
                identifier="habitat-hub",
                clean_session=False,
            ) as client:
                for sub in (*BASE_SUBSCRIPTIONS, *extra_subscriptions):
                    await client.subscribe(sub, qos=1)
                log.info("mqtt connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
                attempt = 0
                pump = asyncio.create_task(publisher._pump(client)) if publisher else None
                reader = asyncio.create_task(_consume(client, ingestor, nodes, handlers))
                waiter = asyncio.create_task(stop.wait())
                try:
                    await asyncio.wait({reader, waiter}, return_when=asyncio.FIRST_COMPLETED)
                    if reader.done() and reader.exception():
                        raise reader.exception()  # type: ignore[misc]
                finally:
                    for t in (pump, reader, waiter):
                        if t is not None:
                            t.cancel()
        except aiomqtt.MqttError as e:
            delay = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
            attempt += 1
            log.warning("mqtt disconnected (%s), retry in %ss", e, delay)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass


async def _consume(
    client: aiomqtt.Client,
    ingestor: Ingestor,
    nodes: NodeRegistry,
    handlers: dict[str, Handler] | None,
) -> None:
    async for message in client.messages:
        payload = message.payload
        if not isinstance(payload, bytes | bytearray):
            payload = b"" if payload is None else str(payload).encode()
        try:
            route_message(ingestor, nodes, str(message.topic), bytes(payload), handlers)
        except Exception:
            log.exception("mqtt message failed on %s", message.topic)
