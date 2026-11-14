"""SQLite store: one shared connection, the hub process is the single writer."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from hub.contract import Reading, Rep
from hub.results import AssessmentResult
from hub.timeutil import to_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node TEXT NOT NULL, boot INTEGER NOT NULL, seq INTEGER NOT NULL, age_ms INTEGER NOT NULL,
  ind TEXT NOT NULL, val REAL NOT NULL, unit TEXT NOT NULL, src TEXT NOT NULL, dev TEXT NOT NULL,
  q TEXT NOT NULL, crew TEXT, code TEXT,
  measured_at TEXT NOT NULL, received_at TEXT NOT NULL,
  derived_from INTEGER REFERENCES readings(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS readings_key ON readings(node, boot, seq)
  WHERE derived_from IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS readings_derived ON readings(derived_from)
  WHERE derived_from IS NOT NULL;
CREATE INDEX IF NOT EXISTS readings_ind_time ON readings(ind, measured_at);
CREATE INDEX IF NOT EXISTS readings_ind_crew_time ON readings(ind, crew, measured_at);
CREATE TABLE IF NOT EXISTS reps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node TEXT NOT NULL, boot INTEGER NOT NULL, seq INTEGER NOT NULL, age_ms INTEGER NOT NULL,
  type TEXT NOT NULL, session TEXT NOT NULL, rep INTEGER NOT NULL, src TEXT NOT NULL,
  peak_n REAL NOT NULL, work_j REAL, rom_m REAL, g REAL NOT NULL, mass_kg REAL NOT NULL,
  t0_ms INTEGER NOT NULL, t1_ms INTEGER NOT NULL,
  measured_at TEXT NOT NULL, received_at TEXT NOT NULL,
  work_ecc_j REAL, t_con_ms INTEGER, t_ecc_ms INTEGER, t_turn_ms INTEGER, exercise TEXT,
  UNIQUE (node, boot, seq)
);
CREATE INDEX IF NOT EXISTS reps_session ON reps(session);
CREATE TABLE IF NOT EXISTS assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reading_id INTEGER NOT NULL REFERENCES readings(id),
  ind TEXT NOT NULL, val REAL, unit TEXT NOT NULL, status TEXT NOT NULL,
  rule_id TEXT, source_kind TEXT, source_ref TEXT, guidance_id TEXT, escalate_to TEXT NOT NULL,
  measured_at TEXT NOT NULL, crew TEXT
);
CREATE INDEX IF NOT EXISTS assessments_reading ON assessments(reading_id);
CREATE INDEX IF NOT EXISTS assessments_rule ON assessments(rule_id, ind, crew, id);
CREATE TABLE IF NOT EXISTS sessions (
  session TEXT PRIMARY KEY, mass_kg REAL NOT NULL, g REAL NOT NULL, crew TEXT,
  started_at TEXT NOT NULL, ended_at TEXT, exercise TEXT
);
CREATE TABLE IF NOT EXISTS food_log (
  meal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  crew TEXT, eaten_at TEXT NOT NULL, created_at TEXT NOT NULL, items TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS food_log_eaten ON food_log(eaten_at);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
"""

_R_COLS = (
    "id, node, boot, seq, age_ms, ind, val, unit, src, dev, q, crew, code, "
    "measured_at, received_at, derived_from"
)
_A_COLS = (
    "id, reading_id, ind, val, unit, status, rule_id, source_kind, source_ref, guidance_id,"
    " escalate_to, measured_at, crew"
)
_P_COLS = (
    "id, node, boot, seq, age_ms, type, session, rep, src, peak_n, work_j, rom_m, g, mass_kg, "
    "t0_ms, t1_ms, measured_at, received_at, work_ecc_j, t_con_ms, t_ecc_ms, t_turn_ms, exercise"
)
_S_COLS = "session, mass_kg, g, crew, started_at, ended_at, exercise"
# Columns added after the first release (D39; exercise pick). Old databases get them through _migrate.
_ADDED_COLS = (
    ("reps", "work_ecc_j", "REAL"), ("reps", "t_con_ms", "INTEGER"),
    ("reps", "t_ecc_ms", "INTEGER"), ("reps", "t_turn_ms", "INTEGER"),
    ("reps", "exercise", "TEXT"), ("sessions", "exercise", "TEXT"),
)  # fmt: skip


def _migrate(conn: sqlite3.Connection) -> None:
    for table, name, kind in _ADDED_COLS:
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


@dataclass(frozen=True)
class StoredReading:
    id: int
    v: int
    node: str
    boot: int
    seq: int
    age_ms: int
    ind: str
    val: float
    unit: str
    src: str
    dev: str
    q: tuple[str, ...]
    crew: str | None
    code: str | None
    measured_at: str
    received_at: str
    derived_from: int | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["q"] = list(self.q)
        return d


@dataclass(frozen=True)
class StoredRep:
    id: int
    v: int
    node: str
    boot: int
    seq: int
    age_ms: int
    type: str
    session: str
    rep: int
    src: str
    peak_n: float
    work_j: float | None
    rom_m: float | None
    g: float
    mass_kg: float
    t0_ms: int
    t1_ms: int
    measured_at: str
    received_at: str
    work_ecc_j: float | None = None
    t_con_ms: int | None = None
    t_ecc_ms: int | None = None
    t_turn_ms: int | None = None
    exercise: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MealRow:
    meal_id: int
    crew: str | None
    eaten_at: str
    created_at: str
    items: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OutboxItem:
    id: int
    kind: str
    created_at: str
    payload: dict


def _reading_row(row: tuple) -> StoredReading:
    return StoredReading(
        id=row[0], v=1, node=row[1], boot=row[2], seq=row[3], age_ms=row[4], ind=row[5],
        val=row[6], unit=row[7], src=row[8], dev=row[9], q=tuple(json.loads(row[10])),
        crew=row[11], code=row[12], measured_at=row[13], received_at=row[14],
        derived_from=row[15],
    )  # fmt: skip


def _rep_row(row: tuple) -> StoredRep:
    return StoredRep(
        id=row[0], v=1, node=row[1], boot=row[2], seq=row[3], age_ms=row[4], type=row[5],
        session=row[6], rep=row[7], src=row[8], peak_n=row[9], work_j=row[10], rom_m=row[11],
        g=row[12], mass_kg=row[13], t0_ms=row[14], t1_ms=row[15], measured_at=row[16],
        received_at=row[17], work_ecc_j=row[18], t_con_ms=row[19], t_ecc_ms=row[20],
        t_turn_ms=row[21], exercise=row[22],
    )  # fmt: skip


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=5.0)
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.executescript(_SCHEMA)
            _migrate(self.conn)
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # readings

    def insert_reading(
        self, r: Reading, received_at: datetime, *, derived_from: int | None = None
    ) -> tuple[StoredReading, bool]:
        measured = to_iso(received_at - timedelta(milliseconds=r.age_ms))
        with self.lock:
            try:
                cur = self.conn.execute(
                    "INSERT INTO readings (node, boot, seq, age_ms, ind, val, unit, src, dev, q,"
                    " crew, code, measured_at, received_at, derived_from)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        r.node, r.boot, r.seq, r.age_ms, r.ind, r.val, r.unit, r.src, r.dev,
                        json.dumps(list(r.q)), r.crew, r.code, measured, to_iso(received_at),
                        derived_from,
                    ),
                )  # fmt: skip
                self.conn.commit()
                row = self.conn.execute(
                    f"SELECT {_R_COLS} FROM readings WHERE id=?", (cur.lastrowid,)
                ).fetchone()
                return _reading_row(row), True
            except sqlite3.IntegrityError:
                self.conn.rollback()
                if derived_from is not None:
                    row = self.conn.execute(
                        f"SELECT {_R_COLS} FROM readings WHERE derived_from=?", (derived_from,)
                    ).fetchone()
                else:
                    row = self.conn.execute(
                        f"SELECT {_R_COLS} FROM readings"
                        " WHERE node=? AND boot=? AND seq=? AND derived_from IS NULL",
                        (r.node, r.boot, r.seq),
                    ).fetchone()
                return _reading_row(row), False

    def get_reading(self, id: int) -> StoredReading | None:
        with self.lock:
            row = self.conn.execute(f"SELECT {_R_COLS} FROM readings WHERE id=?", (id,)).fetchone()
        return _reading_row(row) if row else None

    def readings(
        self,
        ind: str,
        since: datetime | None = None,
        limit: int = 500,
        crew: str | None = None,
    ) -> list[StoredReading]:
        """The latest `limit` rows at or after `since`, in ascending measured_at order."""
        sql = f"SELECT {_R_COLS} FROM readings WHERE ind=?"
        args: list = [ind]
        if since is not None:
            sql += " AND measured_at>=?"
            args.append(to_iso(since))
        if crew is not None:
            sql += " AND crew=?"
            args.append(crew)
        sql += " ORDER BY measured_at DESC, id DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [_reading_row(r) for r in reversed(rows)]

    def readings_between(
        self,
        ind: str,
        start: datetime,
        end: datetime,
        *,
        crew: str | None = None,
        scope_crew: bool = False,
        include_start: bool = False,
        include_end: bool = True,
    ) -> list[StoredReading]:
        """Rows with start < measured_at <= end (bounds adjustable), ascending.

        With scope_crew the crew filter applies, and crew=None then means the crew-null group.
        """
        lo = ">=" if include_start else ">"
        hi = "<=" if include_end else "<"
        sql = (
            f"SELECT {_R_COLS} FROM readings WHERE ind=? AND measured_at{lo}? AND measured_at{hi}?"
        )
        args: list = [ind, to_iso(start), to_iso(end)]
        if scope_crew:
            if crew is None:
                sql += " AND crew IS NULL"
            else:
                sql += " AND crew=?"
                args.append(crew)
        sql += " ORDER BY measured_at, id"
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [_reading_row(r) for r in rows]

    def latest_reading(
        self, ind: str, *, crew: str | None = None, scope_crew: bool = False
    ) -> StoredReading | None:
        sql = f"SELECT {_R_COLS} FROM readings WHERE ind=?"
        args: list = [ind]
        if scope_crew:
            if crew is None:
                sql += " AND crew IS NULL"
            else:
                sql += " AND crew=?"
                args.append(crew)
        sql += " ORDER BY measured_at DESC, id DESC LIMIT 1"
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
        return _reading_row(row) if row else None

    def count(self, table: str) -> int:
        if table not in {"readings", "reps", "outbox", "assessments"}:
            raise ValueError(table)
        with self.lock:
            return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # reps

    def insert_rep(self, r: Rep, received_at: datetime) -> tuple[StoredRep, bool]:
        measured = to_iso(received_at - timedelta(milliseconds=r.age_ms))
        with self.lock:
            try:
                cur = self.conn.execute(
                    "INSERT INTO reps (node, boot, seq, age_ms, type, session, rep, src, peak_n,"
                    " work_j, rom_m, g, mass_kg, t0_ms, t1_ms, measured_at, received_at,"
                    " work_ecc_j, t_con_ms, t_ecc_ms, t_turn_ms, exercise)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        r.node, r.boot, r.seq, r.age_ms, r.type, r.session, r.rep, r.src,
                        r.peak_n, r.work_j, r.rom_m, r.g, r.mass_kg, r.t0_ms, r.t1_ms,
                        measured, to_iso(received_at), r.work_ecc_j, r.t_con_ms, r.t_ecc_ms,
                        r.t_turn_ms, r.exercise,
                    ),
                )  # fmt: skip
                self.conn.commit()
                row = self.conn.execute(
                    f"SELECT {_P_COLS} FROM reps WHERE id=?", (cur.lastrowid,)
                ).fetchone()
                return _rep_row(row), True
            except sqlite3.IntegrityError:
                self.conn.rollback()
                row = self.conn.execute(
                    f"SELECT {_P_COLS} FROM reps WHERE node=? AND boot=? AND seq=?",
                    (r.node, r.boot, r.seq),
                ).fetchone()
                return _rep_row(row), False

    # assessments

    def window_aggregate(
        self,
        ind: str,
        start: datetime | None,
        end: datetime,
        crew: str | None,
        scope_crew: bool,
        fn: Literal["avg", "sum"],
    ) -> tuple[float | None, int, str | None]:
        """(value, row count, earliest measured_at) over assessable rows in (start, end]."""
        agg = "AVG(val)" if fn == "avg" else "SUM(val)"
        sql = (
            f"SELECT {agg}, COUNT(*), MIN(measured_at) FROM readings"
            " WHERE ind=? AND q='[\"ok\"]' AND measured_at<=?"
        )
        args: list = [ind, to_iso(end)]
        if start is not None:
            sql += " AND measured_at>?"
            args.append(to_iso(start))
        if scope_crew:
            if crew is None:
                sql += " AND crew IS NULL"
            else:
                sql += " AND crew=?"
                args.append(crew)
        with self.lock:
            val, n, first = self.conn.execute(sql, args).fetchone()
        return (None if n == 0 else float(val)), n, first

    def insert_assessment(self, a: AssessmentResult) -> AssessmentResult:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO assessments (reading_id, ind, val, unit, status, rule_id,"
                " source_kind, source_ref, guidance_id, escalate_to, measured_at, crew)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    a.reading_id, a.ind, a.val, a.unit, a.status, a.rule_id, a.source_kind,
                    a.source_ref, a.guidance_id, a.escalate_to, a.measured_at, a.crew,
                ),
            )  # fmt: skip
            self.conn.commit()
            new_id = int(cur.lastrowid)
        return AssessmentResult(**{**a.__dict__, "id": new_id})

    def results_for(self, reading_id: int) -> list[AssessmentResult]:
        with self.lock:
            rows = self.conn.execute(
                f"SELECT {_A_COLS} FROM assessments WHERE reading_id=? ORDER BY id",
                (reading_id,),
            ).fetchall()
        return [AssessmentResult(*r) for r in rows]

    def last_status(self, rule_id: str, ind: str, crew: str | None) -> str | None:
        """The latest non-unknown status of a rule for an indicator and crew."""
        sql = "SELECT status FROM assessments WHERE rule_id=? AND ind=? AND status!='unknown'"
        args: list = [rule_id, ind]
        if crew is None:
            sql += " AND crew IS NULL"
        else:
            sql += " AND crew=?"
            args.append(crew)
        sql += " ORDER BY id DESC LIMIT 1"
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
        return row[0] if row else None

    # sessions and reps (H15, H16)

    def insert_session(
        self,
        session: str,
        mass_kg: float,
        g: float,
        crew: str | None,
        started_at: datetime,
        exercise: str | None = None,
    ) -> bool:
        """False when the id already exists."""
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO sessions (session, mass_kg, g, crew, started_at, exercise)"
                    " VALUES (?,?,?,?,?,?)",
                    (session, mass_kg, g, crew, to_iso(started_at), exercise),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                self.conn.rollback()
                return False

    def end_session(self, session: str, ended_at: datetime) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE sessions SET ended_at=? WHERE session=? AND ended_at IS NULL",
                (to_iso(ended_at), session),
            )
            self.conn.commit()

    def session_row(self, session: str) -> tuple | None:
        with self.lock:
            return self.conn.execute(
                f"SELECT {_S_COLS} FROM sessions WHERE session=?",
                (session,),
            ).fetchone()

    def session_rows(self, active_only: bool = False) -> list[tuple]:
        sql = f"SELECT {_S_COLS} FROM sessions"
        if active_only:
            sql += " WHERE ended_at IS NULL"
        sql += " ORDER BY started_at DESC, rowid DESC"
        with self.lock:
            return self.conn.execute(sql).fetchall()

    def rep_counts(self, session: str) -> tuple[int, int]:
        """(camera reps, load-cell reps) as distinct rep numbers per src."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT src, COUNT(DISTINCT rep) FROM reps WHERE session=? GROUP BY src",
                (session,),
            ).fetchall()
        d = dict(rows)
        return d.get("camera", 0), d.get("load_cell", 0)

    def next_rep_seq(self, node: str, boot: int) -> int:
        with self.lock:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM reps WHERE node=? AND boot=?", (node, boot)
            ).fetchone()
        return int(row[0]) + 1

    def reps_for_session(self, session: str) -> list[StoredRep]:
        with self.lock:
            rows = self.conn.execute(
                f"SELECT {_P_COLS} FROM reps WHERE session=? ORDER BY rep, id", (session,)
            ).fetchall()
        return [_rep_row(r) for r in rows]

    def reps_between(self, start: datetime, end: datetime) -> list[StoredRep]:
        """Reps with start < measured_at <= end, all srcs and nodes, ascending."""
        with self.lock:
            rows = self.conn.execute(
                f"SELECT {_P_COLS} FROM reps WHERE measured_at>? AND measured_at<=?"
                " ORDER BY measured_at, id",
                (to_iso(start), to_iso(end)),
            ).fetchall()
        return [_rep_row(r) for r in rows]

    # food log (NU14)

    def insert_meal(
        self, crew: str | None, eaten_at: datetime, created_at: datetime, items: list[dict]
    ) -> int:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO food_log (crew, eaten_at, created_at, items) VALUES (?,?,?,?)",
                (crew, to_iso(eaten_at), to_iso(created_at), json.dumps(items)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def meals_between(self, start: datetime, end: datetime, crew: str | None) -> list[MealRow]:
        """Meals with start < eaten_at <= end, ascending; crew None returns every crew."""
        sql = "SELECT meal_id, crew, eaten_at, created_at, items FROM food_log"
        sql += " WHERE eaten_at>? AND eaten_at<=?"
        args: list = [to_iso(start), to_iso(end)]
        if crew is not None:
            sql += " AND crew=?"
            args.append(crew)
        sql += " ORDER BY eaten_at, meal_id"
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [MealRow(r[0], r[1], r[2], r[3], json.loads(r[4])) for r in rows]

    # outbox

    def append_outbox(self, kind: str, payload: dict, created_at: datetime) -> int:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO outbox (kind, created_at, payload) VALUES (?,?,?)",
                (kind, to_iso(created_at), json.dumps(payload)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def outbox_after(self, after: int, limit: int) -> list[OutboxItem]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, kind, created_at, payload FROM outbox WHERE id>? ORDER BY id LIMIT ?",
                (after, limit),
            ).fetchall()
        return [OutboxItem(r[0], r[1], r[2], json.loads(r[3])) for r in rows]
