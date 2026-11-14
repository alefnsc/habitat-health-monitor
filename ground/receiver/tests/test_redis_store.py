# ground/receiver/tests/test_redis_store.py
from receiver.kv import MemoryKV
from receiver.redis_store import RedisStore

T = "2026-11-14T15:00:00.000Z"


def it(i, crew=None):
    return {"id": i, "kind": "reading", "created_at": T, "payload": {"ind": "hr", "crew": crew}}


def make(cap=20000, now=1_000_000.0):
    clock = {"t": now}
    s = RedisStore(MemoryKV(), cap_items=cap, retention_s=48 * 3600, clock=lambda: clock["t"])
    return s, clock


def test_ingest_and_read_back():
    s, _ = make()
    r = s.ingest({"state": "contact"}, [it(1), it(2)], T)
    assert (r.max_id, r.stored, r.arrival_id) == (2, 2, 1)
    arr = s.arrivals_after(0, 10)
    assert [a.arrival_id for a in arr] == [1]
    assert [x["id"] for x in arr[0].items] == [1, 2]
    assert arr[0].beacon == {"state": "contact"}


def test_resend_is_idempotent():
    s, _ = make()
    s.ingest(None, [it(1), it(2)], T)
    r = s.ingest(None, [it(1), it(2), it(3)], T)
    assert r.stored == 1 and r.max_id == 3
    assert s.summary().stored == 3


def test_beacon_only_arrival_is_logged():
    s, _ = make()
    r = s.ingest({"state": "blackout"}, [], T)
    assert r.stored == 0 and r.max_id is None
    assert s.summary().arrivals == 1


def test_arrivals_after_and_limit():
    s, _ = make()
    for i in range(1, 6):
        s.ingest(None, [it(i)], T)
    assert [a.arrival_id for a in s.arrivals_after(2, 2)] == [3, 4]


def test_summary_fields():
    s, _ = make()
    s.ingest(None, [it(1), it(3)], T)
    sm = s.summary()
    assert (sm.stored, sm.min_id, sm.max_id, sm.missing_ids, sm.arrivals) == (2, 1, 3, 1, 1)
    assert sm.last_arrival_at == T


def test_cap_trims_oldest_arrivals():
    s, _ = make(cap=4)
    s.ingest(None, [it(1), it(2)], T)
    s.ingest(None, [it(3), it(4)], T)
    s.ingest(None, [it(5), it(6)], T)
    sm = s.summary()
    assert sm.stored == 4 and sm.min_id == 3 and sm.max_id == 6
    assert [a.arrival_id for a in s.arrivals_after(0, 10)] == [2, 3]


def test_retention_drops_old_arrivals():
    s, clock = make()
    s.ingest(None, [it(1)], T)
    clock["t"] += 48 * 3600 + 1
    s.ingest(None, [it(2)], T)
    assert [a.arrival_id for a in s.arrivals_after(0, 10)] == [2]
    assert s.summary().min_id == 2


def test_keys_get_48h_ttl():
    kv = MemoryKV()
    s = RedisStore(kv, retention_s=172800, clock=lambda: 1.0)
    s.ingest(None, [it(1)], T)
    assert kv.ttl["g:state"] == 172800 and kv.ttl["g:arrivals"] == 172800


def test_purge_crew():
    s, _ = make()
    s.ingest(None, [it(1, "crew-a"), it(2, "crew-b")], T)
    s.ingest(None, [it(3, "crew-a")], T)
    assert s.purge_crew("crew-a") == 2
    items = [x["id"] for a in s.arrivals_after(0, 10) for x in a.items]
    assert items == [2]
    assert s.summary().stored == 1


def test_arrivals_cap_trims_beacon_only_arrivals():
    s = RedisStore(MemoryKV(), cap_arrivals=2, clock=lambda: 1.0)
    for _ in range(3):
        s.ingest({"state": "contact"}, [], T)
    assert [a.arrival_id for a in s.arrivals_after(0, 10)] == [2, 3]
    assert s.summary().arrivals == 2


def test_within_batch_duplicates_are_stored_once():
    s, _ = make()
    r = s.ingest(None, [it(2), it(2), it(1)], T)
    assert r.stored == 2
    assert [x["id"] for x in s.arrivals_after(0, 10)[0].items] == [1, 2]


def test_purge_crew_survives_null_payload():
    s, _ = make()
    s.ingest(None, [{"id": 1, "kind": "reading", "created_at": T, "payload": None}, it(2, "crew-a")], T)
    assert s.purge_crew("crew-a") == 1
    items = [x["id"] for a in s.arrivals_after(0, 10) for x in a.items]
    assert items == [1]
