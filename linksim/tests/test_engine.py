from datetime import UTC, datetime, timedelta
from pathlib import Path

from linksim.config import Blackout, LinkConfig
from linksim.engine import LinkEngine, OutboxItem

BASE = datetime(2026, 11, 15, 13, 0, 0, tzinfo=UTC)


def wall(t: float) -> str:
    s = (BASE + timedelta(seconds=t)).isoformat(timespec="milliseconds")
    return s.replace("+00:00", "Z")


def engine(blackouts=()):
    cfg = LinkConfig(720.0, 60.0, [Blackout(a, b) for a, b in blackouts])
    return LinkEngine(cfg, 0.0, wall)


def item(i: int) -> OutboxItem:
    return OutboxItem(id=i, kind="reading", created_at=wall(0), payload={"n": i})


def ids(items):
    return [i.id for i in items]


def test_hold_before_due():
    e = engine()
    e.accept([item(1)], 0)
    assert e.due(11.9) == []
    assert ids(e.due(12.0)) == [1]


def test_order_by_id():
    e = engine()
    e.accept([item(3), item(1), item(2)], 0)
    assert ids(e.due(12.0)) == [1, 2, 3]


def test_duplicate_id_once():
    e = engine()
    e.accept([item(5)], 0)
    e.accept([item(5)], 1)
    assert ids(e.due(13.0)) == [5]


def test_blackout_queues():
    e = engine([(30, 60)])
    e.accept([item(1), item(2), item(3)], 35)
    assert e.due(50) == []
    snap = e.snapshot(50)
    assert snap.state == "blackout" and snap.queue_len == 3
    assert e.detail(50).in_flight == 0
    assert e.due(71.9) == []
    assert ids(e.due(72.0)) == [1, 2, 3]


def test_in_flight_survives_blackout():
    e = engine([(30, 60)])
    e.accept([item(1)], 25)
    assert ids(e.due(37.0)) == [1]


def test_failure_keeps_items():
    e = engine()
    e.accept([item(1)], 0)
    assert ids(e.due(12)) == [1]
    e.mark_failed(12)
    snap = e.snapshot(12)
    assert snap.state == "unreachable" and snap.queue_len == 1
    assert ids(e.due(13)) == [1]
    e.mark_delivered([1], 14)
    snap = e.snapshot(14)
    assert snap.state == "contact" and snap.queue_len == 0
    assert snap.last_blackout == {"start": "2026-11-15T13:00:12.000Z", "end": "2026-11-15T13:00:14.000Z"}
    d = e.detail(14)
    assert d.delivered_id == 1 and d.last_blackout_cause == "unreachable"


def test_last_blackout_scheduled():
    e = engine([(30, 60)])
    s45 = e.snapshot(45)
    assert s45.last_blackout == {"start": "2026-11-15T13:00:30.000Z", "end": None}
    assert e.detail(45).last_blackout_cause == "scheduled"
    assert e.snapshot(61).last_blackout == {
        "start": "2026-11-15T13:00:30.000Z",
        "end": "2026-11-15T13:01:00.000Z",
    }
    assert e.snapshot(10).last_blackout is None
    assert e.detail(10).last_blackout_cause is None


def test_snapshot_keys_are_d16():
    d = engine().snapshot(0).to_dict()
    assert set(d) == {"state", "light_time_s", "time_scale", "queue_len", "last_blackout"}


def test_beacons_contact():
    e = engine()
    assert e.due_beacon(11.9) is None
    b = e.due_beacon(12.0)
    assert b is not None and b.sent_at == "2026-11-15T13:00:00.000Z"
    assert e.due_beacon(12.5) is None
    b = e.due_beacon(15.0)
    assert b is not None and b.sent_at == "2026-11-15T13:00:03.000Z"


def test_beacons_blackout():
    e = engine([(30, 60)])
    b = e.due_beacon(41.0)
    assert b is not None
    assert b.sent_at == "2026-11-15T13:00:29.000Z" and b.link.state == "contact"
    for t in (42, 50, 60, 71.9):
        assert e.due_beacon(t) is None
    b = e.due_beacon(72.0)
    assert b is not None and b.sent_at == "2026-11-15T13:01:00.000Z"
    assert b.link.last_blackout["end"] == "2026-11-15T13:01:00.000Z"
    assert b.last_blackout_cause == "scheduled"


def test_no_loss_long_run():
    e = engine([(30, 60)])
    next_id, delivered, dup = 1, [], 0
    seen = set()
    for step in range(801):
        t = step * 0.25
        while next_id <= 1000 and next_id * 0.1 - 0.1 <= t + 1e-9:
            e.accept([item(next_id)], round((next_id - 1) * 0.1, 6))
            next_id += 1
        got = e.due(t)
        if not got:
            continue
        if 70 <= t <= 80:
            e.mark_failed(t)
            continue
        for it in got:
            if it.id in seen:
                dup += 1
            seen.add(it.id)
            delivered.append(it.id)
        e.mark_delivered(ids(got), t)
        assert not set(ids(e.due(t))) & seen
    print(f"delivered {len(seen)}/1000, duplicates {dup}")
    assert sorted(delivered) == list(range(1, 1001))
    assert dup == 0
    assert e.snapshot(200).queue_len == 0
    d = e.detail(200)
    assert d.in_flight == 0 and d.delivered_id == 1000


def test_module_default_file_hold():
    from linksim.config import hold_seconds, load_config

    assert hold_seconds(load_config(Path(__file__).parent.parent / "link.json")) == 12.0
