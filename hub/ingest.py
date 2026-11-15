"""Ingest pipeline: parse, crew fill, store, derive, assess, outbox, emit (H5)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING

from hub.contract import (
    BODY_INDS,
    INTAKE_INDS,
    ContractError,
    Reading,
    parse_reading,
    parse_rep,
    reading_to_dict,
)
from hub.results import Alert, StatusEntry, entry_for
from hub.store import Store, StoredReading, StoredRep

if TYPE_CHECKING:
    from hub.assess import Assessor

log = logging.getLogger("hub.ingest")

CREW_SCOPED = BODY_INDS | INTAKE_INDS
# Streams that are stored but never assessed, outboxed or pushed one by one.
QUIET_INDS = frozenset({"load_raw"})
# Channels fed by hardware nodes, whose (node, boot, seq) key can repeat when a boot counter does
# (tilt-1, bench 2026-11-15). A repeated key with a different sample is stored under a `clash`
# number there; software producers (http, prompt, internal) keep exact idempotency.
NODE_CHANNELS = frozenset({"mqtt", "serial"})


@dataclass
class IngestResult:
    stored: StoredReading | StoredRep | None
    duplicate: bool
    reason: str | None
    results: list[StatusEntry] = field(default_factory=list)
    derived: list[StoredReading] = field(default_factory=list)
    clash: bool = False  # stored, but under a key an earlier, different sample already held


class Ingestor:
    def __init__(
        self,
        store: Store,
        clock: Callable[[], datetime],
        *,
        emit: Callable[[str, dict], None] | None = None,
        deriver: Callable[[Store, StoredReading], StoredReading | None] | None = None,
        assessor: Assessor | None = None,
        crew_for: Callable[[str], str | None] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock
        self.emit = emit
        self.deriver = deriver
        self.assessor = assessor
        self.crew_for = crew_for
        self._listeners: list[Callable[[StoredReading], None]] = []

    def add_listener(self, cb: Callable[[StoredReading], None]) -> None:
        self._listeners.append(cb)

    # entry points

    def ingest_reading(
        self,
        raw: bytes | str | dict,
        *,
        channel: str,
        max_bytes: int | None = None,
        expected_node: str | Collection[str] | None = None,
    ) -> IngestResult:
        try:
            r = parse_reading(raw, max_bytes=max_bytes)
            if expected_node is not None:
                allowed = {expected_node} if isinstance(expected_node, str) else expected_node
                if r.node not in allowed:
                    raise ContractError("topic_node_mismatch")
            return self._pipeline(r, channel)
        except ContractError as e:
            return self._reject(channel, e.reason)
        except Exception:
            log.exception("ingest failed channel=%s", channel)
            return self._reject(channel, "internal_error")

    def ingest_internal(self, r: Reading) -> IngestResult:
        try:
            return self._pipeline(parse_reading(reading_to_dict(r)), "internal")
        except ContractError as e:
            return self._reject("internal", e.reason)
        except Exception:
            log.exception("ingest failed channel=internal")
            return self._reject("internal", "internal_error")

    def ingest_rep(
        self,
        raw: bytes | str | dict,
        *,
        channel: str,
        max_bytes: int | None = None,
        expected_node: str | None = None,
    ) -> IngestResult:
        try:
            rep = parse_rep(raw, max_bytes=max_bytes)
            if expected_node is not None and rep.node != expected_node:
                raise ContractError("topic_node_mismatch")
            now = self.clock()
            stored, new = self.store.insert_rep(rep, now)
            if not new:
                return IngestResult(stored, True, None)
            self.store.append_outbox("rep", stored.to_dict(), now)
            return IngestResult(stored, False, None)
        except ContractError as e:
            return self._reject(channel, e.reason)
        except Exception:
            log.exception("ingest_rep failed channel=%s", channel)
            return self._reject(channel, "internal_error")

    # internals

    def _reject(self, channel: str, reason: str) -> IngestResult:
        log.info("reject channel=%s reason=%s", channel, reason)
        return IngestResult(None, False, reason)

    def _pipeline(self, r: Reading, channel: str) -> IngestResult:
        now = self.clock()
        if r.crew is None and r.ind in CREW_SCOPED and self.crew_for is not None:
            crew = self.crew_for(r.node)
            if crew:
                r = replace(r, crew=crew)
        stored, new = self.store.insert_reading(r, now, allow_clash=channel in NODE_CHANNELS)
        if not new:
            log.info(
                "duplicate channel=%s node=%s boot=%s seq=%s id=%s",
                channel, r.node, r.boot, r.seq, stored.id,
            )  # fmt: skip
            return IngestResult(stored, True, None)
        if stored.clash:
            log.warning(
                "key clash channel=%s node=%s boot=%s seq=%s clash=%s id=%s measured_at=%s",
                channel, r.node, r.boot, r.seq, stored.clash, stored.id, stored.measured_at,
            )  # fmt: skip
        rows = [stored]
        derived: list[StoredReading] = []
        if self.deriver is not None and stored.ind == "cabin_co2":
            d = self.deriver(self.store, stored)
            if d is not None:
                derived.append(d)
                rows.append(d)
        entries: list[StatusEntry] = []
        alerts: list[Alert] = []
        for row in rows:
            if row.ind in QUIET_INDS:
                continue
            results: list = []
            if self.assessor is not None:
                results, row_alerts = self.assessor.assess(row)
                alerts.extend(row_alerts)
            entry = entry_for(row, results)
            entries.append(entry)
            payload = row.to_dict()
            payload.update(
                status=entry.status,
                rule_id=entry.rule_id,
                source_kind=entry.source_kind,
                escalate_to=entry.escalate_to,
            )
            self.store.append_outbox("reading", payload, now)
            if self.emit is not None:
                self.emit("assessment", entry.to_dict())
        if alerts and self.assessor is not None:
            self.assessor.publish_alerts(alerts)
        for row in rows:
            for cb in self._listeners:
                try:
                    cb(row)
                except Exception:
                    log.exception("listener failed")
        return IngestResult(stored, False, None, entries, derived, clash=stored.clash > 0)
