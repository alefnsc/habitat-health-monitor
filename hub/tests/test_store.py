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


# Repeated boot numbers (bench 2026-11-15, validacao-2026-11-15/relatorio-sensores-painel.md, gap 1):
# a node whose boot counter repeats reuses (node, boot, seq) for a different sample.


def tilt(seq: int, val: float, boot: int = 9, age_ms: int = 2):
    return rd(msg(node="tilt-1", boot=boot, seq=seq, age_ms=age_ms, ind="tilt", val=val,
                  unit="state", dev="KY017"))  # fmt: skip


def test_clash_stores_a_different_sample_under_the_same_key(tmp_path):
    s = make(tmp_path)
    a, _ = s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 0), T0 + timedelta(minutes=44), allow_clash=True)
    assert new and b.id != a.id and (a.clash, b.clash) == (0, 1)
    assert [r.val for r in s.readings("tilt")] == [1.0, 0.0]


def test_clash_same_value_far_apart_is_a_new_sample(tmp_path):
    s = make(tmp_path)
    s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 1), T0 + timedelta(minutes=44), allow_clash=True)
    assert new and b.clash == 1


def test_same_value_past_the_window_is_a_new_sample(tmp_path):
    s = make(tmp_path)
    s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 1), T0 + timedelta(seconds=11), allow_clash=True)
    assert new and b.clash == 1


def test_node_retry_with_recomputed_age_is_a_duplicate(tmp_path):
    # HabitatNode re-formats an unacknowledged reading with a fresh age_ms: same measured_at.
    s = make(tmp_path)
    a, _ = s.insert_reading(tilt(1, 1, age_ms=2), T0)
    b, new = s.insert_reading(tilt(1, 1, age_ms=3002), T0 + timedelta(seconds=3), allow_clash=True)
    assert not new and b.id == a.id and s.count("readings") == 1


def test_retry_jitter_inside_the_window_is_a_duplicate(tmp_path):
    s = make(tmp_path)
    a, _ = s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 1), T0 + timedelta(seconds=9), allow_clash=True)
    assert not new and b.id == a.id


def test_same_key_different_value_close_in_time_is_a_clash(tmp_path):
    s = make(tmp_path)
    s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 0), T0 + timedelta(seconds=3), allow_clash=True)
    assert new and b.clash == 1


def test_retry_of_a_clash_row_dedupes_against_it(tmp_path):
    s = make(tmp_path)
    s.insert_reading(tilt(1, 1), T0)
    b, _ = s.insert_reading(tilt(1, 0), T0 + timedelta(minutes=44), allow_clash=True)
    c, new = s.insert_reading(
        tilt(1, 0, age_ms=1002), T0 + timedelta(minutes=44, seconds=1), allow_clash=True
    )
    assert not new and c.id == b.id and s.count("readings") == 2


def test_third_life_of_a_key_gets_clash_2(tmp_path):
    s = make(tmp_path)
    s.insert_reading(tilt(1, 1), T0)
    s.insert_reading(tilt(1, 1), T0 + timedelta(hours=1), allow_clash=True)
    c, new = s.insert_reading(tilt(1, 1), T0 + timedelta(hours=2), allow_clash=True)
    assert new and c.clash == 2 and s.count("readings") == 3


def test_without_allow_clash_the_first_row_wins(tmp_path):
    s = make(tmp_path)
    a, _ = s.insert_reading(tilt(1, 1), T0)
    b, new = s.insert_reading(tilt(1, 0), T0 + timedelta(minutes=44))
    assert not new and b.id == a.id and s.count("readings") == 1


def test_clash_is_in_the_api_dict(tmp_path):
    s = make(tmp_path)
    a, _ = s.insert_reading(tilt(1, 1), T0)
    assert a.to_dict()["clash"] == 0 and s.get_reading(a.id).clash == 0


def test_old_readings_table_gets_clash_column_and_wider_key(tmp_path):
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript(
        "CREATE TABLE readings (id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT NOT NULL,"
        " boot INTEGER NOT NULL, seq INTEGER NOT NULL, age_ms INTEGER NOT NULL, ind TEXT NOT NULL,"
        " val REAL NOT NULL, unit TEXT NOT NULL, src TEXT NOT NULL, dev TEXT NOT NULL,"
        " q TEXT NOT NULL, crew TEXT, code TEXT, measured_at TEXT NOT NULL,"
        " received_at TEXT NOT NULL, derived_from INTEGER REFERENCES readings(id));"
        "CREATE UNIQUE INDEX readings_key ON readings(node, boot, seq) WHERE derived_from IS NULL;"
        "INSERT INTO readings (node, boot, seq, age_ms, ind, val, unit, src, dev, q, measured_at,"
        " received_at) VALUES ('tilt-1', 9, 1, 2, 'tilt', 1, 'state', 'hobby', 'KY017',"
        " '[\"ok\"]', '2026-11-15T13:33:29.000Z', '2026-11-15T13:33:29.002Z');"
    )
    c.commit()
    c.close()
    s = Store(p)
    cols = {row[1] for row in s.conn.execute("PRAGMA table_info(readings)")}
    assert "clash" in cols
    key = [r[2] for r in s.conn.execute("PRAGMA index_info(readings_key)")]
    assert key == ["node", "boot", "seq", "clash"]
    assert s.readings("tilt")[0].clash == 0
    b, new = s.insert_reading(tilt(1, 0), T0 + timedelta(minutes=44), allow_clash=True)
    assert new and b.clash == 1
    s.close()
    s2 = Store(p)  # a second open must not fail or rebuild: the migration is idempotent
    assert s2.count("readings") == 2
    _, dup = s2.insert_reading(tilt(1, 0, age_ms=1002), T0 + timedelta(minutes=44, seconds=1),
                               allow_clash=True)  # fmt: skip
    assert not dup
