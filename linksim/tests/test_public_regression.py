"""Final-review regressions: public path must not depend on local delivery (D38)."""

import tempfile
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from receiver.cloud import create_cloud_app
from receiver.kv import MemoryKV
from receiver.redis_store import RedisStore

from linksim.config import load_config
from linksim.engine import LinkEngine, OutboxItem
from linksim.io import step
from linksim.public import PublicUplink

T = "2026-11-14T15:00:00.000Z"
T0 = 1_000_000.0


def rig(flush_s=0.0):
    eng = LinkEngine(load_config("linksim/link.json"), T0, lambda t: T)
    store = RedisStore(MemoryKV())
    cloud = TestClient(create_cloud_app(store, "k"), base_url="https://x.test")
    up = PublicUplink(cloud, "k", frozenset(), flush_s=flush_s)
    refuse = httpx.Client(
        base_url="http://local.test",
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
    )
    cur = Path(tempfile.mkdtemp()) / "state.json"
    return eng, store, cloud, up, refuse, cur


def test_public_gets_every_item_while_local_refuses():
    eng, store, _, up, refuse, cur = rig()
    hold = eng.detail(T0).hold_s
    now = T0
    for batch in range(4):
        eng.accept(
            [
                OutboxItem(batch * 300 + i, "reading", T, {"ind": "cabin_co2", "node": "cabin-1"})
                for i in range(1, 301)
            ],
            now,
        )
        now += hold + 1
        for _ in range(3):
            step(eng, None, refuse, cur, now, poll=False, public=up)
            now += 1
    for _ in range(4):
        step(eng, None, refuse, cur, now, poll=False, public=up)
        now += 1
    stored_ids = {
        x["id"] for a in store.arrivals_after(0, 1000) for x in a.items
    }
    assert len(stored_ids) == 1200
    assert store.summary().max_id == 1200


def test_real_beacon_reaches_cloud_app():
    eng, store, cloud, up, refuse, cur = rig()
    beacon = eng.due_beacon(T0 + 30.0)
    assert beacon is not None
    up.offer([], beacon)
    assert up.flush(1.0) is True
    arr = cloud.get("/ground/arrivals?after=0").json()
    assert arr[0]["beacon"] == beacon.to_dict()
