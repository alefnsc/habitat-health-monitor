import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta

from hub.contract import parse_rep
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


def rep_msg(**kw) -> dict:
    base = {
        "v": 1, "node": "camera", "boot": 1, "seq": 1, "age_ms": 0, "type": "rep",
        "session": "s1", "rep": 1, "src": "camera", "peak_n": 100.0, "work_j": 10.0,
        "rom_m": 0.5, "g": 9.81, "mass_kg": 10, "t0_ms": 1000, "t1_ms": 3000,
    }  # fmt: skip
    base.update(kw)
    return base


def test_rep_phase_columns_round_trip(tmp_path):
    s = make(tmp_path)
    m = rep_msg(work_ecc_j=20.5, t_con_ms=1000, t_ecc_ms=1000, t_turn_ms=2000)
    row, new = s.insert_rep(parse_rep(m), T0)
    assert new
    assert (row.work_ecc_j, row.t_con_ms, row.t_ecc_ms, row.t_turn_ms) == (20.5, 1000, 1000, 2000)
    assert s.reps_for_session("s1")[0].to_dict()["t_turn_ms"] == 2000
    old, _ = s.insert_rep(parse_rep(rep_msg(seq=2, rep=2)), T0)
    assert (old.work_ecc_j, old.t_con_ms, old.t_ecc_ms, old.t_turn_ms) == (None, None, None, None)


def test_old_reps_table_is_migrated(tmp_path):
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript(
        "CREATE TABLE reps (id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL,"
        " boot INTEGER NOT NULL, seq INTEGER NOT NULL, age_ms INTEGER NOT NULL,"
        " type TEXT NOT NULL, session TEXT NOT NULL, rep INTEGER NOT NULL, src TEXT NOT NULL,"
        " peak_n REAL NOT NULL, work_j REAL, rom_m REAL, g REAL NOT NULL, mass_kg REAL NOT NULL,"
        " t0_ms INTEGER NOT NULL, t1_ms INTEGER NOT NULL, measured_at TEXT NOT NULL,"
        " received_at TEXT NOT NULL, UNIQUE (node, boot, seq));"
        "INSERT INTO reps (node, boot, seq, age_ms, type, session, rep, src, peak_n, work_j,"
        " rom_m, g, mass_kg, t0_ms, t1_ms, measured_at, received_at) VALUES ('camera', 1, 1, 0,"
        " 'rep', 's1', 1, 'camera', 100, 10, 0.5, 9.81, 10, 0, 2000,"
        " '2026-11-14T12:00:00.000Z', '2026-11-14T12:00:00.000Z');"
    )
    c.commit()
    c.close()
    s = Store(p)
    (r,) = s.reps_for_session("s1")
    assert r.work_j == 10 and r.t_turn_ms is None
    s.close()
    s2 = Store(p)  # a second open must not fail: the migration is idempotent
    cols = {row[1] for row in s2.conn.execute("PRAGMA table_info(reps)")}
    assert {"work_ecc_j", "t_con_ms", "t_ecc_ms", "t_turn_ms"} <= cols
    row, _ = s2.insert_rep(parse_rep(rep_msg(seq=2, rep=2, t_turn_ms=1500)), T0)
    assert row.t_turn_ms == 1500


def test_rep_exercise_round_trip(tmp_path):
    s = make(tmp_path)
    row, _ = s.insert_rep(parse_rep(rep_msg(exercise="row")), T0)
    assert row.exercise == "row"
    assert s.reps_for_session("s1")[0].to_dict()["exercise"] == "row"
    old, _ = s.insert_rep(parse_rep(rep_msg(seq=2, rep=2)), T0)
    assert old.exercise is None


def test_session_exercise_round_trip(tmp_path):
    s = make(tmp_path)
    assert s.insert_session("s1", 10, 9.81, None, T0, exercise="curl")
    assert s.insert_session("s2", 10, 9.81, None, T0)
    assert s.session_row("s1")[6] == "curl"
    assert s.session_row("s2")[6] is None


def test_old_tables_get_exercise_columns(tmp_path):
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript(
        "CREATE TABLE sessions (session TEXT PRIMARY KEY, mass_kg REAL NOT NULL,"
        " g REAL NOT NULL, crew TEXT, started_at TEXT NOT NULL, ended_at TEXT);"
        "INSERT INTO sessions (session, mass_kg, g, started_at)"
        " VALUES ('old', 10, 9.81, '2026-11-14T12:00:00.000Z');"
    )
    c.commit()
    c.close()
    s = Store(p)
    assert s.session_row("old")[6] is None
    s.close()
    s2 = Store(p)  # idempotent
    for table in ("reps", "sessions"):
        cols = {row[1] for row in s2.conn.execute(f"PRAGMA table_info({table})")}
        assert "exercise" in cols
    row, _ = s2.insert_rep(parse_rep(rep_msg(exercise="curl")), T0)
    assert row.exercise == "curl"
