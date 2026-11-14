"""Link engine: light-time hold, blackout queue, no loss. Pure and deterministic.

Times are caller-supplied seconds (`now_s`); there is no I/O and no real clock.
Blackouts in the config are seconds after `start_s`.
"""

from __future__ import annotations

import functools
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .config import LinkConfig, hold_seconds, in_blackout

MAX_DUE = 500
MAX_PENDING_BEACONS = 2000


@dataclass(frozen=True)
class OutboxItem:
    """One hub outbox row (resolution D1)."""

    id: int
    kind: Literal["reading", "rep", "alert", "prompt_answer"]
    created_at: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LinkState:
    """Exactly resolution D16, no extra keys."""

    state: Literal["contact", "blackout", "unreachable"]
    light_time_s: float
    time_scale: float
    queue_len: int
    last_blackout: dict[str, str | None] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Beacon:
    """Internal linksim to ground status message."""

    link: LinkState
    hold_s: float
    in_flight: int
    fetched_id: int
    delivered_id: int
    last_blackout_cause: Literal["scheduled", "unreachable"] | None
    sent_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Rec:
    item: OutboxItem
    accepted_at: float
    transmit_at: float
    arrive_at: float


@dataclass
class _Episode:
    start: float
    end: float | None = None


@dataclass
class _BeaconSlot:
    sent: float
    arrive: float
    beacon: Beacon


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper


@dataclass
class LinkEngine:
    cfg: LinkConfig
    start_s: float
    wall: Callable[[float], str]
    _pending: dict[int, _Rec] = field(default_factory=dict, init=False)
    _delivered: set[int] = field(default_factory=set, init=False)
    _fetched_id: int = field(default=0, init=False)
    _delivered_id: int = field(default=0, init=False)
    _failures: list[_Episode] = field(default_factory=list, init=False)
    _beacons: deque[_BeaconSlot] = field(default_factory=deque, init=False)
    _next_beacon_k: int = field(default=0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    @property
    def fetched_id(self) -> int:
        """Highest outbox id accepted; the hub poll cursor."""
        return self._fetched_id

    @fetched_id.setter
    def fetched_id(self, value: int) -> None:
        self._fetched_id = value

    # ----- helpers -----

    def _hold(self) -> float:
        return hold_seconds(self.cfg)

    def _elapsed(self, t: float) -> float:
        return t - self.start_s

    def _transmit_time(self, t: float) -> float:
        """Accept time if in contact, otherwise the end of the blackout run."""
        e = self._elapsed(t)
        while (b := in_blackout(self.cfg, e)) is not None:
            e = b.end
        return self.start_s + e

    def _scheduled_episode(self, t: float) -> tuple[float, float | None] | None:
        e = self._elapsed(t)
        latest = None
        for b in self.cfg.blackouts:
            if b.start <= e:
                latest = b
        if latest is None:
            return None
        end = None if e < latest.end else self.start_s + latest.end
        return self.start_s + latest.start, end

    def _last_episode(self, t: float) -> tuple[float, float | None, str] | None:
        cands: list[tuple[float, float | None, str]] = []
        sched = self._scheduled_episode(t)
        if sched:
            cands.append((sched[0], sched[1], "scheduled"))
        for ep in self._failures:
            if ep.start <= t:
                end = ep.end if ep.end is not None and ep.end <= t else None
                cands.append((ep.start, end, "unreachable"))
        if not cands:
            return None
        return max(cands, key=lambda c: c[0])

    def _unreachable_at(self, t: float) -> bool:
        return any(
            ep.start <= t and (ep.end is None or t < ep.end) for ep in self._failures
        )

    def _link_state(self, t: float) -> LinkState:
        if in_blackout(self.cfg, self._elapsed(t)) is not None:
            state: Literal["contact", "blackout", "unreachable"] = "blackout"
        elif self._unreachable_at(t):
            state = "unreachable"
        else:
            state = "contact"
        queue_len = sum(
            1
            for r in self._pending.values()
            if r.accepted_at <= t and (r.transmit_at > t or r.arrive_at <= t)
        )
        ep = self._last_episode(t)
        last = (
            None
            if ep is None
            else {
                "start": self.wall(ep[0]),
                "end": None if ep[1] is None else self.wall(ep[1]),
            }
        )
        return LinkState(state, self.cfg.light_time_s, self.cfg.time_scale, queue_len, last)

    def _detail(self, t: float) -> Beacon:
        in_flight = sum(
            1
            for r in self._pending.values()
            if r.accepted_at <= t and r.transmit_at <= t < r.arrive_at
        )
        ep = self._last_episode(t)
        return Beacon(
            link=self._link_state(t),
            hold_s=self._hold(),
            in_flight=in_flight,
            fetched_id=self._fetched_id,
            delivered_id=self._delivered_id,
            last_blackout_cause=None if ep is None else ep[2],  # type: ignore[arg-type]
            sent_at=self.wall(t),
        )

    def _generate_beacons(self, now_s: float) -> None:
        """Create one beacon per whole second since start, none during a blackout."""
        while self.start_s + self._next_beacon_k <= now_s:
            sent = self.start_s + self._next_beacon_k
            self._next_beacon_k += 1
            if in_blackout(self.cfg, self._elapsed(sent)) is not None:
                continue
            self._beacons.append(_BeaconSlot(sent, sent + self._hold(), self._detail(sent)))
            if len(self._beacons) > MAX_PENDING_BEACONS:
                self._beacons.popleft()

    # ----- public API -----

    @_locked
    def accept(self, items: list[OutboxItem], now_s: float) -> None:
        self._generate_beacons(now_s)
        for it in items:
            if it.id in self._delivered or it.id in self._pending:
                continue
            tx = self._transmit_time(now_s)
            self._pending[it.id] = _Rec(it, now_s, tx, tx + self._hold())
            self._fetched_id = max(self._fetched_id, it.id)

    @_locked
    def due(self, now_s: float, limit: int | None = MAX_DUE) -> list[OutboxItem]:
        """Crossed items in id order; `limit=None` returns every ready item."""
        self._generate_beacons(now_s)
        ready = sorted(r.item.id for r in self._pending.values() if r.arrive_at <= now_s)
        return [self._pending[i].item for i in (ready if limit is None else ready[:limit])]

    @_locked
    def due_beacon(self, now_s: float) -> Beacon | None:
        self._generate_beacons(now_s)
        newest = None
        while self._beacons and self._beacons[0].arrive <= now_s:
            newest = self._beacons.popleft()
        return None if newest is None else newest.beacon

    @_locked
    def mark_delivered(self, ids: list[int], now_s: float) -> None:
        self._generate_beacons(now_s)
        for i in ids:
            if self._pending.pop(i, None) is not None:
                self._delivered.add(i)
                self._delivered_id = max(self._delivered_id, i)
        for ep in self._failures:
            if ep.end is None:
                ep.end = now_s

    @_locked
    def mark_failed(self, now_s: float) -> None:
        self._generate_beacons(now_s)
        if not any(ep.end is None for ep in self._failures):
            self._failures.append(_Episode(now_s))

    @_locked
    def snapshot(self, now_s: float) -> LinkState:
        self._generate_beacons(now_s)
        return self._link_state(now_s)

    @_locked
    def detail(self, now_s: float) -> Beacon:
        self._generate_beacons(now_s)
        return self._detail(now_s)
