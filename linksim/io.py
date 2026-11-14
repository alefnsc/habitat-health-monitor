"""Link simulator I/O: poll the hub outbox, forward due items to ground, persist a cursor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from .engine import LinkEngine, OutboxItem

if TYPE_CHECKING:
    from .public import PublicUplink

BATCH = 500


class LinkDown(Exception):
    """The ground side could not be reached or refused the batch."""


def fetch_outbox(client: httpx.Client, hub: str, after: int, limit: int) -> list[OutboxItem]:
    """GET /api/outbox. Returns [] when the hub is down; only trusts `items`."""
    try:
        res = client.get(f"{hub}/api/outbox", params={"after": after, "limit": limit})
        res.raise_for_status()
        raw = res.json()["items"]
        return [
            OutboxItem(
                id=int(d["id"]), kind=d["kind"], created_at=d["created_at"], payload=d["payload"]
            )
            for d in raw
        ]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []


def post_ground(
    client: httpx.Client, ground: str, beacon, items: list[OutboxItem]
) -> int | None:
    """POST /ground/ingest. Returns the receiver's max_id; raises LinkDown on any failure."""
    body = {
        "beacon": None if beacon is None else beacon.to_dict(),
        "items": [
            {"id": i.id, "kind": i.kind, "created_at": i.created_at, "payload": i.payload}
            for i in items
        ],
    }
    try:
        res = client.post(f"{ground}/ground/ingest", json=body)
        res.raise_for_status()
        return res.json().get("max_id")
    except (httpx.HTTPError, ValueError) as exc:
        raise LinkDown(str(exc)) from exc


def load_cursor(path: Path) -> int:
    try:
        return int(json.loads(Path(path).read_text())["delivered_id"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def save_cursor(path: Path, delivered_id: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"delivered_id": delivered_id}))
    tmp.replace(path)


def step(
    engine: LinkEngine,
    hub_client: httpx.Client | None,
    ground_client: httpx.Client | None,
    cursor: Path,
    now_s: float,
    poll: bool = True,
    public: PublicUplink | None = None,
) -> None:
    """One tick: poll the hub, hand crossed items to the public uplink, deliver locally.

    `ground_client=None` means there is no local ground receiver: crossed items count as
    delivered. The public uplink never blocks local delivery.
    """
    if poll and hub_client is not None:
        engine.accept(fetch_outbox(hub_client, "", engine.fetched_id, BATCH), now_s)
    items = engine.due(now_s)
    beacon = engine.due_beacon(now_s)
    if public is not None:
        # Public sees every crossed item, even while local delivery keeps failing.
        public.offer(engine.due(now_s, limit=None), beacon)
    try:
        _deliver_local(engine, ground_client, cursor, now_s, items, beacon)
    finally:
        if public is not None:
            public.flush(now_s)


def _deliver_local(engine, ground_client, cursor, now_s, items, beacon) -> None:
    if not items and beacon is None:
        return
    if ground_client is not None:
        try:
            post_ground(ground_client, "", beacon, items)
        except LinkDown:
            engine.mark_failed(now_s)
            return
    engine.mark_delivered([i.id for i in items], now_s)
    if items:
        save_cursor(cursor, max(i.id for i in items))
