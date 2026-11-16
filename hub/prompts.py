"""Self-check prompts: morning, post-exercise, cabin trigger, with linked answers (H18, D6)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from hub.config import Settings
from hub.contract import CABIN_INDS, CREWS, ContractError, parse_reading, reading_to_dict
from hub.exercise import Session
from hub.ingest import Ingestor
from hub.results import Alert, entry_for
from hub.store import Store
from hub.timeutil import parse_iso, to_iso

log = logging.getLogger("hub.prompts")

PROMPT_ASKS: dict[str, tuple[str, ...]] = {
    "morning": ("body_temp", "hr", "sleep_h", "mood"),
    "post_exercise": ("hr", "symptom"),
    "cabin_trigger": ("symptom",),
    # D45: opened only by hub/signals/trigger.py, always with the signal snapshot as `trigger`.
    "signal_cabin": ("symptom",),
    "signal_body": ("symptom", "mood"),
}
SIGNAL_KINDS = frozenset({"signal_cabin", "signal_body"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, asks TEXT NOT NULL, crew TEXT,
  status TEXT NOT NULL, created_at TEXT NOT NULL, trigger_reading_id INTEGER, rule_id TEXT,
  trigger TEXT
);
CREATE TABLE IF NOT EXISTS prompt_answers (
  prompt_id INTEGER NOT NULL REFERENCES prompts(id), reading_id INTEGER NOT NULL,
  PRIMARY KEY (prompt_id, reading_id)
);
"""
_COLS = "id, kind, asks, crew, status, created_at, trigger_reading_id, rule_id, trigger"


class PromptError(ValueError):
    def __init__(self, reason: str, status: int = 422) -> None:
        super().__init__(reason)
        self.reason, self.status = reason, status


@dataclass(frozen=True)
class Prompt:
    id: int
    kind: str
    asks: list[str]
    crew: str | None
    status: Literal["open", "answered", "skipped"]
    created_at: str
    trigger_reading_id: int | None
    rule_id: str | None
    trigger: dict | None

    def to_dict(self) -> dict:
        return asdict(self)


def _prompt(row: tuple) -> Prompt:
    return Prompt(
        id=row[0], kind=row[1], asks=json.loads(row[2]), crew=row[3], status=row[4],
        created_at=row[5], trigger_reading_id=row[6], rule_id=row[7],
        trigger=json.loads(row[8]) if row[8] else None,
    )  # fmt: skip


class PromptService:
    def __init__(
        self,
        store: Store,
        ingestor: Ingestor,
        settings: Settings,
        clock: Callable[[], datetime],
        emit: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.store, self.ingestor, self.settings, self.clock, self.emit = (
            store, ingestor, settings, clock, emit,
        )  # fmt: skip
        self.tz = ZoneInfo(settings.tz)
        with store.lock:
            store.conn.executescript(_SCHEMA)
            store.conn.commit()

    # reads

    def get(self, prompt_id: int) -> Prompt | None:
        with self.store.lock:
            row = self.store.conn.execute(
                f"SELECT {_COLS} FROM prompts WHERE id=?", (prompt_id,)
            ).fetchone()
        return _prompt(row) if row else None

    def pending(self, crew: str | None, status: str = "open") -> list[Prompt]:
        if status not in ("open", "all"):
            raise PromptError("bad_value:status")
        sql = f"SELECT {_COLS} FROM prompts"
        where, args = [], []
        if status == "open":
            where.append("status='open'")
        if crew is not None:
            where.append("(crew=? OR crew IS NULL)")
            args.append(crew)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        with self.store.lock:
            rows = self.store.conn.execute(sql, args).fetchall()
        return [_prompt(r) for r in rows]

    def _frame(self, p: Prompt) -> None:
        if self.emit is not None:
            self.emit("prompt", p.to_dict())

    # creation

    def create(
        self,
        kind: str,
        crew: str | None,
        *,
        trigger_reading_id: int | None = None,
        rule_id: str | None = None,
        trigger: dict | None = None,
    ) -> Prompt:
        if kind not in PROMPT_ASKS:
            raise PromptError("bad_value:kind")
        if (kind in SIGNAL_KINDS) != (trigger is not None):
            raise PromptError("bad_value:kind")  # signal prompts come only from the trigger
        if crew is not None and crew not in CREWS:
            raise PromptError("bad_crew")
        if trigger_reading_id is not None:
            r = self.store.get_reading(trigger_reading_id)
            if r is not None:
                trigger = entry_for(r, self.store.results_for(r.id)).to_dict()
        with self.store.lock:
            cur = self.store.conn.execute(
                "INSERT INTO prompts (kind, asks, crew, status, created_at, trigger_reading_id,"
                " rule_id, trigger) VALUES (?,?,?,?,?,?,?,?)",
                (
                    kind, json.dumps(list(PROMPT_ASKS[kind])), crew, "open", to_iso(self.clock()),
                    trigger_reading_id, rule_id, json.dumps(trigger) if trigger else None,
                ),
            )  # fmt: skip
            self.store.conn.commit()
            pid = int(cur.lastrowid)
        p = self.get(pid)
        assert p is not None
        self._frame(p)
        return p

    def _set_status(self, prompt_id: int, status: str) -> None:
        with self.store.lock:
            self.store.conn.execute("UPDATE prompts SET status=? WHERE id=?", (status, prompt_id))
            self.store.conn.commit()

    def tick(self, now: datetime) -> list[Prompt]:
        local = now.astimezone(self.tz)
        if local.time() < self.settings.morning_at:
            return []
        created: list[Prompt] = []
        for crew in self.settings.crews:
            todays = [
                p for p in self.pending(None, "all")
                if p.kind == "morning" and p.crew == crew
                and parse_iso(p.created_at).astimezone(self.tz).date() == local.date()
            ]  # fmt: skip
            if todays:
                continue
            for old in self.pending(None, "open"):
                if old.kind == "morning" and old.crew == crew:
                    self._set_status(old.id, "skipped")
                    updated = self.get(old.id)
                    assert updated is not None
                    self._frame(updated)
            created.append(self.create("morning", crew))
        return created

    def on_alert(self, a: Alert) -> Prompt | None:
        if a.ind not in CABIN_INDS or a.status not in ("watch", "act"):
            return None
        for p in self.pending(None, "open"):
            if p.kind == "cabin_trigger" and p.rule_id == a.rule_id:
                return None
        with self.store.lock:
            row = self.store.conn.execute(
                "SELECT reading_id FROM assessments WHERE id=?", (a.id,)
            ).fetchone()
        return self.create(
            "cabin_trigger", None, trigger_reading_id=row[0] if row else None, rule_id=a.rule_id
        )

    def on_session_end(self, s: Session) -> Prompt | None:
        return self.create("post_exercise", s.crew)

    # answers

    def answer(self, prompt_id: int, readings: list, skipped: bool = False) -> dict:
        p = self.get(prompt_id)
        if p is None:
            raise PromptError("unknown_prompt", 404)
        if p.status != "open":
            raise PromptError("already_answered", 409)
        if skipped and readings:
            raise PromptError("bad_value:skipped")
        if not skipped and not readings:
            raise PromptError("bad_value:readings")
        parsed = []
        for raw in readings:
            if not isinstance(raw, dict):
                raise PromptError("bad_type:readings")
            try:
                r = parse_reading(raw)
            except ContractError as e:
                raise PromptError(e.reason) from None
            if r.ind not in p.asks:
                raise PromptError("ind_not_asked")
            if p.crew is not None and r.crew not in (None, p.crew):
                raise PromptError("crew_mismatch")
            d = reading_to_dict(r)
            if p.crew is not None:
                d["crew"] = p.crew
            parsed.append(d)
        ids: list[int] = []
        entries: list[dict] = []
        for d in parsed:
            res = self.ingestor.ingest_reading(d, channel="prompt")
            if res.reason is not None or res.stored is None:
                raise PromptError(res.reason or "internal_error")
            ids.append(res.stored.id)
            entries.extend(e.to_dict() for e in res.results)
        status = "skipped" if skipped else "answered"
        now = self.clock()
        payload = {
            "prompt_id": p.id, "prompt_kind": p.kind, "crew": p.crew, "status": status,
            "reading_ids": ids, "trigger_reading_id": p.trigger_reading_id,
            "rule_id": p.rule_id, "answered_at": to_iso(now),
        }  # fmt: skip
        with self.store.lock:
            try:
                for rid in ids:
                    self.store.conn.execute(
                        "INSERT OR IGNORE INTO prompt_answers (prompt_id, reading_id) VALUES (?,?)",
                        (p.id, rid),
                    )
                self.store.conn.execute("UPDATE prompts SET status=? WHERE id=?", (status, p.id))
                self.store.conn.execute(
                    "INSERT INTO outbox (kind, created_at, payload) VALUES (?,?,?)",
                    ("prompt_answer", to_iso(now), json.dumps(payload)),
                )
                self.store.conn.commit()
            except Exception:
                self.store.conn.rollback()
                raise
        updated = self.get(p.id)
        assert updated is not None
        self._frame(updated)
        return {"prompt_id": p.id, "reading_ids": ids, "results": entries}

    def answer_links(self, prompt_id: int) -> list[int]:
        with self.store.lock:
            rows = self.store.conn.execute(
                "SELECT reading_id FROM prompt_answers WHERE prompt_id=? ORDER BY reading_id",
                (prompt_id,),
            ).fetchall()
        return [r[0] for r in rows]
