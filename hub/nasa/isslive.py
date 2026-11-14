"""ISS Live parsing and latest-value state (N8b). No network code: the client drives `update`."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Item ids from docs/nasa/isslive-probe.md. TIME_000001 is never subscribed (about 20 updates/s).
ISS_ITEMS: dict[str, str] = {
    "USLAB000058": "cabin_pressure",
    "USLAB000059": "cabin_temperature",
    "USLAB000055": "lab_ppco2",
    "NODE3000003": "node3_ppco2",
}


def iss_timestamp_to_utc(ts: float, now: datetime) -> datetime:
    """TimeStamp = day-of-year x 24 + UTC hours, day 1 = 1 January. Previous year if > 1 day ahead."""
    now = now.astimezone(UTC)

    def for_year(year: int) -> datetime:
        return datetime(year, 1, 1, tzinfo=UTC) + timedelta(hours=ts - 24)

    t = for_year(now.year)
    if t - now > timedelta(days=1):
        t = for_year(now.year - 1)
    return t


def parse_value(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


@dataclass(frozen=True)
class IssItemUpdate:
    item: str
    val: float
    ts: float
    measured_at: datetime
    status_class: str | None
    received_at: datetime


class IssLiveState:
    def __init__(self) -> None:
        self._latest: dict[str, IssItemUpdate] = {}
        self._lock = threading.Lock()
        self.connected = False
        self.started_at: datetime | None = None
        self.last_message_at: datetime | None = None
        self.last_connected_at: datetime | None = None

    def update(
        self,
        item: str,
        raw_ts: str,
        raw_val: str | None,
        status_class: str | None,
        received_at: datetime,
    ) -> bool:
        val = parse_value(raw_val)
        ts = parse_value(raw_ts)
        if val is None or ts is None:
            return False
        u = IssItemUpdate(
            item, val, ts, iss_timestamp_to_utc(ts, received_at), status_class, received_at
        )
        with self._lock:
            self._latest[item] = u
            self.last_message_at = received_at
        return True

    def latest(self) -> dict[str, IssItemUpdate]:
        with self._lock:
            return dict(self._latest)
