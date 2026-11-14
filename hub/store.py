"""SQLite store: one shared connection, the hub process is the single writer."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hub.contract import Reading, Rep
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
  UNIQUE (node, boot, seq)
);
CREATE INDEX IF NOT EXISTS reps_session ON reps(session);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
"""

_R_COLS = (
    "id, node, boot, seq, age_ms, ind, val, unit, src, dev, q, crew, code, "
    "measured_at, received_at, derived_from"
)
_P_COLS = (
    "id, node, boot, seq, age_ms, type, session, rep, src, peak_n, work_j, rom_m, g, mass_kg, "
    "t0_ms, t1_ms, measured_at, received_at"
)


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
        received_at=row[17],
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
        if table not in {"readings", "reps", "outbox"}:
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
                    " work_j, rom_m, g, mass_kg, t0_ms, t1_ms, measured_at, received_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        r.node, r.boot, r.seq, r.age_ms, r.type, r.session, r.rep, r.src,
                        r.peak_n, r.work_j, r.rom_m, r.g, r.mass_kg, r.t0_ms, r.t1_ms,
                        measured, to_iso(received_at),
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
