import json

import httpx
import respx
from fastapi.testclient import TestClient
from receiver.cloud import create_cloud_app
from receiver.kv import MemoryKV
from receiver.redis_store import RedisStore
from receiver.signing import HEADER, sign

from linksim.engine import OutboxItem
from linksim.public import PublicUplink

T = "2026-11-14T15:00:00.000Z"
URL = "https://ground.example.test"


def oi(i, **payload):
    return OutboxItem(id=i, kind="reading", created_at=T, payload=payload)


def uplink(client, crews=frozenset(), flush_s=10.0, **kw):
    return PublicUplink(client, "k", crews, flush_s=flush_s, **kw)


def test_offer_filters_and_dedupes():
    up = uplink(httpx.Client(base_url=URL))
    up.offer([oi(1, ind="cabin_temp"), oi(2, ind="hr", crew="crew-b")], None)
    up.offer([oi(1, ind="cabin_temp"), oi(3, ind="cabin_rh")], None)
    assert [i.id for i in up.queue] == [1, 3]
    assert up.filtered == 1 and up.offered_id == 3


def test_flush_waits_for_interval_and_signs():
    with respx.mock(base_url=URL) as mock:
        route = mock.post("/ground/ingest").respond(200, json={"max_id": 1, "stored": 1})
        up = uplink(httpx.Client(base_url=URL))
        up.offer([oi(1, ind="cabin_temp")], None)
        assert up.flush(100.0) is True
        req = route.calls.last.request
        assert req.headers[HEADER] == sign(req.content, "k")
        assert json.loads(req.content)["items"][0]["id"] == 1
        up.offer([oi(2, ind="cabin_temp")], None)
        assert up.flush(105.0) is False
        assert up.flush(110.0) is True
        assert up.delivered_id == 2 and up.queue == []


def test_failure_keeps_queue():
    with respx.mock(base_url=URL) as mock:
        mock.post("/ground/ingest").respond(503)
        up = uplink(httpx.Client(base_url=URL), flush_s=0.0)
        up.offer([oi(1, ind="cabin_temp")], None)
        assert up.flush(1.0) is False
        assert up.failures == 1 and len(up.queue) == 1


def test_queue_overflow_drops_oldest():
    up = uplink(httpx.Client(base_url=URL), max_queue=2)
    up.offer([oi(1, ind="cabin_temp"), oi(2, ind="cabin_temp"), oi(3, ind="cabin_temp")], None)
    assert [i.id for i in up.queue] == [2, 3] and up.overflow == 1


def test_end_to_end_into_cloud_app():
    app = create_cloud_app(RedisStore(MemoryKV()), "k")
    client = TestClient(app, base_url=URL)
    up = uplink(client, crews=frozenset({"crew-a"}), flush_s=0.0)
    up.offer(
        [
            oi(1, ind="cabin_co2", node="cabin-1"),
            oi(2, ind="hr", node="vitals-1", crew="crew-a"),
            oi(3, ind="hr", node="vitals-1", crew="crew-b"),
            oi(4, ind="hr", node="sim-1", crew="crew-b"),
        ],
        None,
    )
    assert up.flush(1.0) is True
    ids = [x["id"] for a in client.get("/ground/arrivals?after=0").json() for x in a["items"]]
    assert ids == [1, 2, 4]


def test_step_feeds_public_and_local_optional(monkeypatch):
    from linksim import io as lio

    class FakeEngine:
        fetched_id = 0

        def accept(self, items, now_s):
            pass

        def due(self, now_s):
            return [oi(7, ind="cabin_temp")]

        def due_beacon(self, now_s):
            return None

        def mark_delivered(self, ids, now_s):
            self.delivered = ids

        def mark_failed(self, now_s):
            self.failed = True

    class FakeUp:
        def __init__(self):
            self.offered, self.flushed = [], 0

        def offer(self, items, beacon):
            self.offered += [i.id for i in items]

        def flush(self, now_s):
            self.flushed += 1
            return True

    saved = []
    monkeypatch.setattr(lio, "save_cursor", lambda p, i: saved.append(i))
    eng, up = FakeEngine(), FakeUp()
    lio.step(eng, None, None, "cursor", 1.0, poll=False, public=up)
    assert up.offered == [7] and up.flushed == 1
    assert eng.delivered == [7] and saved == [7]


def test_flush_never_raises_on_bad_beacon():
    class Bad:
        def to_dict(self):
            raise RuntimeError("boom")

    up = uplink(httpx.Client(base_url=URL), flush_s=0.0)
    up.offer([oi(1, ind="cabin_temp")], Bad())
    assert up.flush(1.0) is False
    assert up.failures == 1


def test_step_delivers_locally_when_public_flush_raises(monkeypatch):
    from linksim import io as lio

    class FakeEngine:
        fetched_id = 0

        def due(self, now_s):
            return [oi(7, ind="cabin_temp")]

        def due_beacon(self, now_s):
            return None

        def mark_delivered(self, ids, now_s):
            self.delivered = ids

    class BadUp:
        def offer(self, items, beacon):
            pass

        def flush(self, now_s):
            raise RuntimeError("boom")

    monkeypatch.setattr(lio, "save_cursor", lambda p, i: None)
    eng = FakeEngine()
    try:
        lio.step(eng, None, None, "cursor", 1.0, poll=False, public=BadUp())
    except RuntimeError:
        pass
    assert eng.delivered == [7]


def test_4xx_drops_chunk_and_counts_rejected():
    with respx.mock(base_url=URL) as mock:
        route = mock.post("/ground/ingest")
        route.side_effect = [httpx.Response(401), httpx.Response(200, json={})]
        up = uplink(httpx.Client(base_url=URL), flush_s=0.0, batch=1)
        up.offer([oi(1, ind="cabin_temp"), oi(2, ind="cabin_temp")], None)
        assert up.flush(1.0) is False
        assert up.rejected == 1 and [i.id for i in up.queue] == [2] and up.delivered_id == 0
        assert up.flush(2.0) is True
        assert up.delivered_id == 2


def test_backoff_doubles_after_failure():
    with respx.mock(base_url=URL) as mock:
        route = mock.post("/ground/ingest").respond(503)
        up = uplink(httpx.Client(base_url=URL), flush_s=10.0)
        up.offer([oi(1, ind="cabin_temp")], None)
        assert up.flush(100.0) is False
        assert route.call_count == 1
        assert up.flush(110.0) is False
        assert route.call_count == 1
        assert up.flush(120.0) is False
        assert route.call_count == 2


def test_backoff_exponent_is_capped_and_resets():
    with respx.mock(base_url=URL) as mock:
        mock.post("/ground/ingest").respond(200, json={})
        up = uplink(httpx.Client(base_url=URL), flush_s=10.0)
        up._backoff = 5000
        assert up._interval() == 60.0
        up.offer([oi(1, ind="cabin_temp")], None)
        assert up.flush(1000.0) is True
        assert up._backoff == 0


def test_3xx_is_a_failure():
    with respx.mock(base_url=URL) as mock:
        mock.post("/ground/ingest").respond(302)
        up = uplink(httpx.Client(base_url=URL), flush_s=0.0)
        up.offer([oi(1, ind="cabin_temp")], None)
        assert up.flush(1.0) is False
        assert up.failures == 1 and len(up.queue) == 1
