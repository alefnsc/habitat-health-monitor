"""UTC timestamp helpers. Wire format: YYYY-MM-DDTHH:MM:SS.mmmZ."""

from __future__ import annotations

from datetime import UTC, datetime


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("to_iso needs an aware datetime")
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_iso(s: str) -> datetime:
    """Parse an ISO 8601 timestamp; a missing zone means UTC. Raises ValueError."""
    if not isinstance(s, str) or not s:
        raise ValueError("empty timestamp")
    text = s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
