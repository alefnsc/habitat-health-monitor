"""SQLite store for the ground receiver: idempotent items plus an arrivals log."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS arrivals (
  arrival_id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT NOT NULL,
  beacon TEXT,
  item_ids TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class IngestResult:
    max_id: int | None
    stored: int
    arrival_id: int


@dataclass(frozen=True)
class Arrival:
    arrival_id: int
    received_at: str
    beacon: dict[str, Any] | None
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class Summary:
    stored: int
    min_id: int | None
    max_id: int | None
    missing_ids: int
    arrivals: int
    last_arrival_at: str | None


def utc_now() -> str:
    """Receiver clock, `YYYY-MM-DDTHH:MM:SS.mmmZ`."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def open_db(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def ingest(
    conn: sqlite3.Connection,
    beacon: dict | None,
    items: list[dict],
    received_at: str,
) -> IngestResult:
    """Store items (re-sends are ignored) and log one arrival."""
    new_ids: list[int] = []
    conn.execute("BEGIN")
    try:
        for it in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO items (id, kind, created_at, payload) VALUES (?, ?, ?, ?)",
                (it["id"], it["kind"], it["created_at"], json.dumps(it["payload"])),
            )
            if cur.rowcount:
                new_ids.append(it["id"])
        cur = conn.execute(
            "INSERT INTO arrivals (received_at, beacon, item_ids) VALUES (?, ?, ?)",
            (received_at, None if beacon is None else json.dumps(beacon), json.dumps(new_ids)),
        )
        arrival_id = cur.lastrowid
        max_id = conn.execute("SELECT MAX(id) FROM items").fetchone()[0]
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return IngestResult(max_id, len(new_ids), arrival_id)


def arrivals_after(conn: sqlite3.Connection, after: int, limit: int) -> list[Arrival]:
    rows = conn.execute(
        "SELECT arrival_id, received_at, beacon, item_ids FROM arrivals "
        "WHERE arrival_id > ? ORDER BY arrival_id LIMIT ?",
        (after, limit),
    ).fetchall()
    out: list[Arrival] = []
    for arrival_id, received_at, beacon, item_ids in rows:
        ids = json.loads(item_ids)
        items: list[dict[str, Any]] = []
        for i in ids:
            row = conn.execute(
                "SELECT id, kind, created_at, payload FROM items WHERE id = ?", (i,)
            ).fetchone()
            items.append(
                {"id": row[0], "kind": row[1], "created_at": row[2], "payload": json.loads(row[3])}
            )
        out.append(
            Arrival(arrival_id, received_at, None if beacon is None else json.loads(beacon), items)
        )
    return out


def summary(conn: sqlite3.Connection) -> Summary:
    stored, min_id, max_id = conn.execute("SELECT COUNT(*), MIN(id), MAX(id) FROM items").fetchone()
    arrivals, last = conn.execute("SELECT COUNT(*), MAX(received_at) FROM arrivals").fetchone()
    missing = 0 if stored == 0 else (max_id - min_id + 1) - stored
    return Summary(stored, min_id, max_id, missing, arrivals, last)
