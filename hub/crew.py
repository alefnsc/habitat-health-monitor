"""Crew attribution: badge messages and the console selector (D11)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from hub.contract import CREWS, NODES, ContractError, _check_fields, _decode
from hub.store import Store
from hub.timeutil import to_iso

log = logging.getLogger("hub.crew")

_BADGE_FIELDS = (("v", "int"), ("node", "str"), ("boot", "int"), ("seq", "int"), ("crew", "str"))


@dataclass(frozen=True)
class Badge:
    v: int
    node: str
    boot: int
    seq: int
    crew: str


def parse_badge(raw: bytes | str | dict, *, expected_node: str | None = None) -> Badge:
    msg = _decode(raw, 256 if not isinstance(raw, dict) else None)
    _check_fields(msg, _BADGE_FIELDS)
    if expected_node is not None and msg["node"] != expected_node:
        raise ContractError("topic_node_mismatch")
    if msg["crew"] not in CREWS:
        raise ContractError("bad_crew")
    return Badge(1, msg["node"], msg["boot"], msg["seq"], msg["crew"])


class CrewRegistry:
    def __init__(self, store: Store, clock: Callable[[], datetime]) -> None:
        self.store = store
        self.clock = clock
        with store.lock:
            store.conn.execute(
                "CREATE TABLE IF NOT EXISTS current_crew ("
                "node TEXT PRIMARY KEY, crew TEXT NOT NULL, set_at TEXT NOT NULL)"
            )
            store.conn.commit()
            rows = store.conn.execute("SELECT node, crew FROM current_crew").fetchall()
        self._crew: dict[str, str] = dict(rows)

    def set(self, node: str, crew: str | None) -> None:
        with self.store.lock:
            if crew is None:
                self.store.conn.execute("DELETE FROM current_crew WHERE node=?", (node,))
            else:
                self.store.conn.execute(
                    "INSERT INTO current_crew (node, crew, set_at) VALUES (?,?,?) "
                    "ON CONFLICT(node) DO UPDATE SET crew=excluded.crew, set_at=excluded.set_at",
                    (node, crew, to_iso(self.clock())),
                )
            self.store.conn.commit()
        if crew is None:
            self._crew.pop(node, None)
        else:
            self._crew[node] = crew

    def get(self, node: str) -> str | None:
        return self._crew.get(node)

    def snapshot(self) -> dict[str, str]:
        return dict(self._crew)

    def on_badge(self, b: Badge) -> None:
        self.set(b.node, b.crew)

    def handle_badge_message(self, node: str, payload: bytes) -> None:
        """MQTT handler for habitat/v1/badge/<node>; a bad badge is only logged."""
        try:
            self.on_badge(parse_badge(payload, expected_node=node))
        except ContractError as e:
            log.info("reject channel=badge reason=%s", e.reason)


def validate_crew_post(body: object) -> tuple[str, str | None]:
    if not isinstance(body, dict):
        raise ContractError("bad_json")
    if "node" not in body:
        raise ContractError("missing_field:node")
    if "crew" not in body:
        raise ContractError("missing_field:crew")
    node, crew = body["node"], body["crew"]
    if not isinstance(node, str):
        raise ContractError("bad_type:node")
    if node not in NODES:
        raise ContractError("unknown_node")
    if crew is not None and crew not in CREWS:
        raise ContractError("bad_crew")
    return node, crew
