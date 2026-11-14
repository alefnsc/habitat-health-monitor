import threading
import time
from datetime import UTC, datetime, timedelta

from hub.store import Store
from hub.tests.helpers import hr, msg, reading

T0 = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)


def rd(d: dict):
    return reading(**d)


def make(tmp_path):
    return Store(tmp_path / "t.db")


def test_wal_mode(tmp_path):
    s = make(tmp_path)
    assert s.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_measured_at(tmp_path):
    s = make(tmp_path)
    row, new = s.insert_reading(rd(hr(age_ms=5000)), T0 + timedelta(seconds=5))
    assert new
    assert row.measured_at == "2026-11-14T12:00:00.000Z"
    assert row.received_at == "2026-11-14T12:00:05.000Z"


def test_idempotent_key(tmp_path):
    s = make(tmp_path)
    a, n1 = s.insert_reading(rd(hr(seq=17, val=72)), T0)
    b, n2 = s.insert_reading(rd(hr(seq=17, val=99)), T0)
    assert n1 and not n2 and a.id == b.id and b.val == 72.0
    assert len(s.readings("hr")) == 1


def test_new_boot_same_seq(tmp_path):
    s = make(tmp_path)
    s.insert_reading(rd(hr(seq=17)), T0)
    _, new = s.insert_reading(rd({**hr(seq=17), "boot": 4}), T0)
    assert new


def test_seq_is_per_message(tmp_path):
    s = make(tmp_path)
    s.insert_reading(rd(msg(ind="cabin_temp", unit="C", val=22.0, dev="BME280")), T0)
    _, new = s.insert_reading(rd(msg(ind="cabin_rh", unit="%", val=45, dev="BME280")), T0)
    assert not new and s.readings("cabin_rh") == []


def test_derived_row(tmp_path):
    s = make(tmp_path)
    p, _ = s.insert_reading(rd(msg()), T0)
    d = rd(msg(ind="cabin_co2"))
    derived = d.__class__(**{**d.__dict__, "ind": "cabin_ppco2", "unit": "mmHg", "val": 3.0})
    row, new = s.insert_reading(derived, T0, derived_from=p.id)
    assert new and row.derived_from == p.id
    _, new2 = s.insert_reading(derived, T0, derived_from=p.id)
    assert not new2


def test_flags_roundtrip(tmp_path):
    s = make(tmp_path)
    row, _ = s.insert_reading(rd(hr(q=["motion", "no_contact"])), T0)
    assert row.q == ("motion", "no_contact")
    assert s.get_reading(row.id).q == ("motion", "no_contact")


def three(s):
    for i, m in enumerate((0, 1, 2)):
        s.insert_reading(rd(hr(seq=i + 1, val=60 + i)), T0 + timedelta(minutes=m))


def test_history_order_and_limit(tmp_path):
    s = make(tmp_path)
    three(s)
    rows = s.readings("hr", limit=2)
    assert [r.val for r in rows] == [61.0, 62.0]


def test_since_inclusive(tmp_path):
    s = make(tmp_path)
    three(s)
    rows = s.readings("hr", since=T0 + timedelta(minutes=1))
    assert [r.val for r in rows] == [61.0, 62.0]


def test_crew_filter(tmp_path):
    s = make(tmp_path)
    s.insert_reading(rd(hr(seq=1, val=60, crew="crew-a")), T0)
    s.insert_reading(rd(hr(seq=2, val=70, crew="crew-b")), T0)
    assert [r.val for r in s.readings("hr", crew="crew-a")] == [60.0]


def test_outbox_append_and_cursor(tmp_path):
    s = make(tmp_path)
    ids = [
        s.append_outbox("reading", {"id": 1}, T0),
        s.append_outbox("reading", {"id": 2}, T0),
        s.append_outbox("rep", {"id": 1}, T0),
    ]
    items = s.outbox_after(0, 100)
    assert [i.id for i in items] == sorted(ids) and len({i.id for i in items}) == 3
    assert [i.kind for i in items] == ["reading", "reading", "rep"]
    assert items[0].payload == {"id": 1}
    assert [i.id for i in s.outbox_after(items[0].id, 100)] == ids[1:]
    s.insert_reading(rd(hr()), T0)
    assert s.count("outbox") == 3


def test_reopen(tmp_path):
    s = make(tmp_path)
    for i in range(3):
        s.insert_reading(rd(hr(seq=17 + i)), T0)
    s.close()
    s = make(tmp_path)
    assert len(s.readings("hr")) == 3
    _, new = s.insert_reading(rd(hr(seq=17)), T0)
    assert not new


def test_concurrent_writers(tmp_path):
    s = make(tmp_path)
    errors = []

    def work(k):
        try:
            for i in range(250):
                s.insert_reading(rd(hr(seq=k * 1000 + i + 1)), T0)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and s.count("readings") == 1000


def test_throughput(tmp_path):
    s = make(tmp_path)
    t = time.perf_counter()
    for i in range(800):
        s.insert_reading(
            rd(msg(node="exercise-1", boot=1, seq=i + 1, ind="load_raw", unit="N", val=50,
                   dev="HX711")),
            T0,
        )  # fmt: skip
    assert time.perf_counter() - t < 2.0
