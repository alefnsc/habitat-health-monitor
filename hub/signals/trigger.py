"""The self-check trigger (D45 §8). A notable signal may open a prompt; it never raises an alert.

Every state change of a ★ signal is logged in signal_events. A prompt opens only on a change from
`steady` to `notable`, when no prompt for that signal and crew is open, after the cooldown, and
never for a replay signal (synthetic data does not ask a real crew how they feel). Replay and real
events keep separate histories, so a replay `steady` is never the baseline for a real `notable`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from hub.signals.catalogue import CATALOGUE
from hub.signals.engine import evaluate
from hub.signals.types import Signal
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import parse_iso, to_iso

log = logging.getLogger("hub.signals.trigger")

TRIGGER_IDS: tuple[str, ...] = tuple(s.id for s in CATALOGUE if s.can_trigger)
COOLDOWN = {"signal_cabin": timedelta(hours=2), "signal_body": timedelta(hours=24)}
PERIOD_S = 300

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL, crew TEXT, state TEXT NOT NULL,
  replay INTEGER NOT NULL, at TEXT NOT NULL, prompt_id INTEGER, snapshot TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS signal_events_key ON signal_events(signal_id, crew, replay, id);
"""


def kind_for(s: Signal) -> str:
    return "signal_cabin" if s.crew is None else "signal_body"


def snapshot(s: Signal, at: datetime) -> dict:
    """What the console shows next to the self-check: no series, no pairs."""
    d = s.to_dict()
    return {
        "signal_id": s.id, "state": s.state, "headline_key": s.headline_key, "value": d["value"],
        "inputs": d["inputs"], "limits": d["limits"], "reference": d["reference"],
        "replay": s.replay, "at": to_iso(at),
    }  # fmt: skip


class SignalTrigger:
    def __init__(
        self, store: Store, rules: Sequence[Rule], prompts, *, crews: Sequence[str], tz: str,
        clock: Callable[[], datetime],
    ) -> None:  # fmt: skip
        self.store, self.rules, self.prompts = store, rules, prompts
        self.crews, self.tz, self.clock = list(crews), tz, clock
        self.period_s = PERIOD_S
        with store.lock:
            store.conn.executescript(_SCHEMA)
            store.conn.commit()

    def _last(self, s: Signal, with_prompt: bool = False) -> tuple | None:
        sql = "SELECT state, at, prompt_id FROM signal_events WHERE signal_id=? AND replay=?"
        args: list = [s.id, int(s.replay)]
        crew = s.crew
        sql += " AND crew IS NULL" if crew is None else " AND crew=?"
        if crew is not None:
            args.append(crew)
        if with_prompt:
            sql += " AND prompt_id IS NOT NULL"
        sql += " ORDER BY id DESC LIMIT 1"
        with self.store.lock:
            return self.store.conn.execute(sql, args).fetchone()

    def _log(self, s: Signal, at: datetime, prompt_id: int | None, snap: dict) -> None:
        with self.store.lock:
            self.store.conn.execute(
                "INSERT INTO signal_events (signal_id, crew, state, replay, at, prompt_id, snapshot)"
                " VALUES (?,?,?,?,?,?,?)",
                (s.id, s.crew, s.state, int(s.replay), to_iso(at), prompt_id, json.dumps(snap)),
            )
            self.store.conn.commit()

    def _open_for(self, s: Signal) -> bool:
        for p in self.prompts.pending(s.crew):
            if (
                p.crew == s.crew
                and p.kind == kind_for(s)
                and (p.trigger or {}).get("signal_id") == s.id
            ):
                return True
        return False

    def _cooling(self, s: Signal, now: datetime) -> bool:
        last = self._last(s, with_prompt=True)
        return last is not None and now - parse_iso(last[1]) < COOLDOWN[kind_for(s)]

    def step(self, s: Signal, now: datetime):
        """Log a state change and maybe open a prompt; returns the prompt or None."""
        last = self._last(s)
        prev = last[0] if last else None
        if prev == s.state:
            return None
        snap = snapshot(s, now)
        prompt = None
        if (s.state == "notable" and prev == "steady" and not s.replay
                and not self._open_for(s) and not self._cooling(s, now)):  # fmt: skip
            prompt = self.prompts.create(kind_for(s), s.crew, trigger=snap)
        self._log(s, now, prompt.id if prompt else None, snap)
        return prompt

    def tick(self, now: datetime | None = None) -> list:
        now = now or self.clock()
        out = []
        for s in evaluate(self.store, self.rules, crews=self.crews, at=now, tz=self.tz,
                          ids=TRIGGER_IDS):  # fmt: skip
            try:
                p = self.step(s, now)
            except Exception:
                log.exception("signal trigger failed for %s %s", s.id, s.crew)
                continue
            if p is not None:
                out.append(p)
        return out
