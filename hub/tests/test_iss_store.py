from datetime import timedelta

import pytest

from hub.nasa.iss_store import IssWriter, to_hub_unit
from hub.nasa.isslive import IssItemUpdate
from hub.tests.helpers import Rig, T


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


def upd(item, val, at, received=None):
    return IssItemUpdate(item, val, 0.0, at, None, received or at + timedelta(seconds=2))


def send(rig, w, u):
    """Deliver an update as the client does: the hub clock reads the update's arrival time."""
    rig.clock.set(u.received_at)
    return w.on_update(u)


def test_pressure_is_stored_in_hpa_and_quiet(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert send(rig, w, upd("USLAB000058", 760.0, T))
    [r] = rig.store.readings("iss_cabin_p")
    assert r.val == pytest.approx(1013.25, abs=0.01) and r.unit == "hPa"
    assert (r.node, r.src, r.dev, r.crew) == ("nasa", "nasa", "ISSLIVE", None)
    assert rig.store.count("outbox") == 0 and rig.store.count("assessments") == 0


def test_one_row_per_item_per_minute(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert send(rig, w, upd("USLAB000055", 2.1, T))
    assert not send(rig, w, upd("USLAB000055", 2.2, T + timedelta(seconds=30)))
    assert send(rig, w, upd("NODE3000003", 2.4, T + timedelta(seconds=30)))  # another item
    assert send(rig, w, upd("USLAB000055", 2.3, T + timedelta(seconds=61)))
    # Lab and Node 3 are two modules: never one series (review 2026-11-15)
    assert [r.val for r in rig.store.readings("iss_ppco2")] == [2.1, 2.3]
    assert [r.val for r in rig.store.readings("iss_ppco2_node3")] == [2.4]


def test_stale_and_unknown_items_are_skipped(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert not send(rig, w, upd("USLAB000059", 21.0, T, received=T + timedelta(minutes=11)))
    assert not send(rig, w, upd("TIME_000001", 1.0, T))
    assert rig.store.count("readings") == 0


def test_temperature_and_ppco2_keep_their_units():
    assert to_hub_unit("cabin_temperature", 21.5) == 21.5
    assert to_hub_unit("lab_ppco2", 2.7) == 2.7


def test_a_future_dated_update_is_skipped_and_does_not_block_the_item(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    future = upd("USLAB000055", 9.9, T + timedelta(hours=20), received=T)  # bad clock on the feed
    assert not send(rig, w, future)
    assert send(rig, w, upd("USLAB000055", 2.2, T + timedelta(minutes=2)))
    assert [r.val for r in rig.store.readings("iss_ppco2")] == [2.2]
