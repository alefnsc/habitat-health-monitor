"""DONKI disk cache (task N2): one JSON file per kind, written atomically, with cached_at."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hub.nasa.donki import DonkiResult

log = logging.getLogger(__name__)

STALE_LIMIT_S = 1800  # three missed 10-minute polls


@dataclass(frozen=True)
class CachedDonki:
    kind: str
    events: list[dict]
    route: str
    cached_at: datetime


def is_stale(cached_at: datetime, now: datetime, limit_s: int = STALE_LIMIT_S) -> bool:
    return (now - cached_at).total_seconds() > limit_s


class DonkiCache:
    def __init__(self, dir: Path) -> None:
        self.dir = Path(dir)

    def _path(self, kind: str) -> Path:
        return self.dir / f"donki_{kind}.json"

    def write(self, result: DonkiResult) -> None:
        events = result.events
        if result.kind == "notifications":  # display only; drop the long bodies
            events = [{k: v for k, v in e.items() if k != "messageBody"} for e in events]
        payload = {
            "kind": result.kind,
            "route": result.route,
            "cached_at": result.fetched_at.astimezone(UTC).isoformat(),
            "events": events,
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=f"donki_{result.kind}", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, self._path(result.kind))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def read(self, kind: str) -> CachedDonki | None:
        path = self._path(kind)
        try:
            raw = json.loads(path.read_text())
            return CachedDonki(
                kind=raw["kind"],
                events=list(raw["events"]),
                route=raw["route"],
                cached_at=datetime.fromisoformat(raw["cached_at"]),
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("DONKI cache %s unreadable: %s", path.name, exc)
            return None
