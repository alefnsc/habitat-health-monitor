import json
import logging
import random

import pytest

from hub.contract import Reading, parse_rep
from hub.derive import derive_ppco2
from hub.ingest import Ingestor
from hub.store import Store
from hub.tests.helpers import msg

REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


@pytest.fixture
def events():
    return []


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "i.db")


@pytest.fixture
def ing(store, clock, events):
    return Ingestor(store, clock, emit=lambda t, d: events.append((t, d)), deriver=derive_ppco2)


def temp(**kw):
    return msg(ind="cabin_temp", unit="C", val=22.0, dev="BME280", **kw)


def test_pipeline_new_reading(ing, store, events):
    res = ing.ingest_reading(json.dumps(temp()), channel="http")
    assert res.reason is None and not res.duplicate
    assert len(res.results) == 1
    e = res.results[0]
    assert e.status == "unknown" and e.reading_id == res.stored.id
    assert events == [("assessment", e.to_dict())]
    items = store.outbox_after(0, 10)
    assert len(items) == 1 and items[0].kind == "reading"
    p = items[0].payload
    assert p["id"] == res.stored.id and p["val"] == 22.0 and p["measured_at"]
    assert (p["status"], p["rule_id"], p["source_kind"], p["escalate_to"]) == (
        "unknown", None, None, "self",
    )  # fmt: skip


def test_duplicate_quiet(ing, store, events):
    ing.ingest_reading(temp(), channel="http")
    events.clear()
    res = ing.ingest_reading(temp(), channel="http")
    assert res.duplicate and res.results == [] and events == []
    assert store.count("outbox") == 1


def test_load_raw_quiet(ing, store, events):
    seen = []
    ing.add_listener(seen.append)
    m = msg(node="exercise-1", boot=1, seq=1, ind="load_raw", unit="N", val=120, dev="HX711")
    res = ing.ingest_reading(m, channel="serial")
    assert res.reason is None and res.stored is not None
    assert store.count("outbox") == 0 and events == []
    assert [s.id for s in seen] == [res.stored.id]


def test_rep_outbox(ing, store, events):
    res = ing.ingest_rep(REP, channel="http")
    assert res.reason is None and res.results == [] and events == []
    (item,) = store.outbox_after(0, 10)
    assert item.kind == "rep" and item.payload["rep"] == 1 and item.payload["id"] == res.stored.id
    assert ing.ingest_rep(REP, channel="http").duplicate


def test_expected_node(ing, store):
    res = ing.ingest_reading(
        msg(node="vitals-1", ind="hr", unit="bpm", val=70, dev="MAX30102"),
        channel="mqtt",
        expected_node="cabin-1",
    )
    assert res.reason == "topic_node_mismatch" and store.count("readings") == 0


def test_expected_node_collection(ing, store):
    both = {"exercise-1", "cabin-1"}
    ok = ing.ingest_reading(msg(node="cabin-1"), channel="serial", expected_node=both)
    assert ok.reason is None
    bad = ing.ingest_reading(
        msg(node="vitals-1", ind="hr", unit="bpm", val=70, dev="MAX30102"),
        channel="serial",
        expected_node=both,
    )
    assert bad.reason == "topic_node_mismatch"


def test_ingest_internal(ing, store, events):
    r = Reading(1, "nasa", 0, 1763121600000, 0, "space_weather", 2.0, "level", "nasa", "DONKI",
                ("ok",), None, None)  # fmt: skip
    res = ing.ingest_internal(r)
    assert res.reason is None and store.count("readings") == 1
    assert events and events[0][0] == "assessment"
    bad = ing.ingest_internal(Reading(**{**r.__dict__, "unit": "mSv", "seq": 2}))
    assert bad.reason == "unit_mismatch" and store.count("readings") == 1


def test_ingest_internal_intake(ing, store, events):
    r = Reading(1, "food", 1794657600, 1, 7200000, "intake_sodium_mg", 210.0, "mg", "self",
                "catalog", ("ok",), "crew-a", None)  # fmt: skip
    res = ing.ingest_internal(r)
    assert res.reason is None
    assert res.stored.measured_at == "2026-11-14T10:00:00.000Z"
    assert store.count("outbox") == 1 and events[0][0] == "assessment"
    bad = ing.ingest_internal(Reading(**{**r.__dict__, "val": 30000.1, "seq": 2}))
    assert bad.reason == "bad_value:val" and store.count("readings") == 1


def test_crew_fill(store, clock):
    ing = Ingestor(store, clock, crew_for=lambda n: "crew-b" if n == "vitals-1" else None)

    def hr(node, crew=None, seq=1):
        return msg(node=node, seq=seq, ind="hr", unit="bpm", val=70,
                   dev="manual" if node == "manual" else "MAX30102", crew=crew)  # fmt: skip

    assert ing.ingest_reading(hr("vitals-1"), channel="mqtt").stored.crew == "crew-b"
    assert ing.ingest_reading(hr("vitals-1", "crew-a", 2), channel="mqtt").stored.crew == "crew-a"
    assert ing.ingest_reading(temp(), channel="mqtt").stored.crew is None
    assert ing.ingest_reading(hr("manual", seq=3), channel="http").stored.crew is None


def test_crew_fill_intake(store, clock):
    ing = Ingestor(store, clock, crew_for=lambda n: "crew-b" if n == "manual" else None)
    kc = msg(node="manual", ind="intake_kcal", unit="kcal", val=500, src="self", dev="manual")
    assert ing.ingest_reading(kc, channel="http").stored.crew == "crew-b"
    bm = msg(node="manual", seq=2, ind="body_mass", unit="kg", val=70, src="self", dev="manual")
    assert ing.ingest_reading(bm, channel="http").stored.crew == "crew-b"
    ct = msg(node="manual", seq=3, ind="cabin_temp", unit="C", val=22, dev="manual")
    assert ing.ingest_reading(ct, channel="http").stored.crew is None


def test_never_raises(ing, store):
    rnd = random.Random(42)
    blobs = [bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 301))) for _ in range(50)]
    blobs += [b"", b"null", b"[]", b"x" * 10240]
    reasons = []
    for b in blobs:
        res = ing.ingest_reading(b, channel="mqtt", max_bytes=256)
        assert res.reason is not None
        reasons.append(res.reason)
    assert reasons[-1] == "too_large"
    assert store.count("readings") == 0
    assert parse_rep(REP)  # sanity: the rep fixture stays valid


def test_derived_in_pipeline(ing, store, events, clock):
    ing.ingest_reading(msg(ind="cabin_p", unit="hPa", val=1000.0, dev="BME280", seq=1),
                       channel="mqtt")  # fmt: skip
    clock.advance(30)
    events.clear()
    res = ing.ingest_reading(msg(seq=2, val=4000), channel="mqtt")
    assert [e.ind for e in res.results] == ["cabin_co2", "cabin_ppco2"]
    assert [t for t, _ in events] == ["assessment", "assessment"]
    assert store.count("outbox") == 3


# Repeated boot numbers (bench 2026-11-15, validacao-2026-11-15/relatorio-sensores-painel.md, gap 1).


def tilt(seq, val, boot=9, age_ms=2):
    return msg(node="tilt-1", boot=boot, seq=seq, age_ms=age_ms, ind="tilt", val=val,
               unit="state", dev="KY017")  # fmt: skip


def test_repeated_boot_number_is_stored_with_a_clash_warning(ing, store, events, clock, caplog):
    ing.ingest_reading(tilt(1, 1), channel="mqtt")
    clock.advance(44 * 60)
    events.clear()
    with caplog.at_level(logging.WARNING, logger="hub.ingest"):
        res = ing.ingest_reading(tilt(1, 0), channel="mqtt")
    assert res.reason is None and not res.duplicate and res.clash
    assert res.stored.clash == 1 and res.stored.val == 0.0
    assert [e.ind for e in res.results] == ["tilt"] and events[0][0] == "assessment"
    assert store.count("readings") == 2 and store.count("outbox") == 2
    assert "clash channel=mqtt node=tilt-1 boot=9 seq=1" in caplog.text


def test_node_retry_is_a_quiet_duplicate_with_a_log_line(ing, store, events, clock, caplog):
    ing.ingest_reading(tilt(1, 1, age_ms=2), channel="mqtt")
    clock.advance(3)
    events.clear()
    with caplog.at_level(logging.INFO, logger="hub.ingest"):
        res = ing.ingest_reading(tilt(1, 1, age_ms=3002), channel="mqtt")
    assert res.duplicate and not res.clash and res.results == [] and events == []
    assert store.count("readings") == 1 and store.count("outbox") == 1
    assert "duplicate channel=mqtt node=tilt-1 boot=9 seq=1" in caplog.text


def test_http_key_reuse_stays_a_duplicate(ing, store, clock):
    # Software producers pick their keys for idempotency; only node channels widen the key.
    ing.ingest_reading(temp(), channel="http")
    clock.advance(44 * 60)
    res = ing.ingest_reading({**temp(), "val": 23.0}, channel="http")
    assert res.duplicate and not res.clash and store.count("readings") == 1


def test_serial_channel_widens_the_key(ing, store, clock):
    line = msg(node="cabin-1", boot=14, seq=1, ind="cabin_temp", unit="C", val=25.3, dev="DHT11")
    ing.ingest_reading(line, channel="serial")
    clock.advance(600)
    res = ing.ingest_reading({**line, "val": 24.9}, channel="serial")
    assert res.clash and res.stored.clash == 1 and store.count("readings") == 2
