"""DONKI client (task N1): keyless CCMC host first, keyed api.nasa.gov as the second route.

Sources (recorded for DATA_SOURCES.md):
- https://ccmc.gsfc.nasa.gov/DONKI-API/get/{FLR,SEP,GST,notifications}?startDate=&endDate=
- https://api.nasa.gov/DONKI/{kind} with a personal NASA_API_KEY (never DEMO_KEY)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import httpx

if TYPE_CHECKING:
    from hub.nasa.config import NasaSettings
    from hub.nasa.donki_cache import CachedDonki, DonkiCache

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 600
POLL_WINDOW_DAYS = 7

DONKI_KINDS: tuple[str, ...] = ("FLR", "SEP", "GST", "notifications")
MAX_WINDOW_DAYS = 60  # probed 2026-11-14: 60 days answers 200, 61 days answers 400
KEYED_BASE = "https://api.nasa.gov/DONKI"
TIMEOUT_S = 10.0


class DonkiUnavailable(Exception):
    """No DONKI route returned usable data."""


@dataclass(frozen=True)
class DonkiResult:
    kind: str
    events: list[dict]
    route: Literal["direct", "api_key"]
    fetched_at: datetime


def donki_url(base: str, kind: str, start: date, end: date) -> str:
    return f"{base.rstrip('/')}/{kind}?startDate={start.isoformat()}&endDate={end.isoformat()}"


def _check(kind: str, start: date, end: date) -> None:
    if kind not in DONKI_KINDS:
        raise ValueError(f"unknown DONKI kind {kind!r}")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError("window exceeds 60 days")
    if end < start:
        raise ValueError("end is before start")


def _usable_key(key: str | None) -> bool:
    return bool(key) and key.strip().upper() != "DEMO_KEY"


def _events(resp: httpx.Response) -> list[dict]:
    body = resp.json()
    if not isinstance(body, list):
        raise DonkiUnavailable("DONKI answered with a non-list body")
    return body


async def donki_fetch(
    kind: str,
    start: date,
    end: date,
    *,
    client: httpx.AsyncClient,
    base: str,
    api_key: str | None,
    now: datetime | None = None,
) -> DonkiResult:
    _check(kind, start, end)
    fetched_at = now or datetime.now(UTC)
    direct_error: str
    try:
        r = await client.get(donki_url(base, kind, start, end))
        if r.status_code == 200:
            return DonkiResult(kind, _events(r), "direct", fetched_at)
        direct_error = f"HTTP {r.status_code}"
        if r.status_code < 500:  # a 4xx is our request, not an outage: no second route
            raise DonkiUnavailable(f"DONKI {kind} direct host: {direct_error}")
    except httpx.HTTPError as exc:
        direct_error = type(exc).__name__
    except ValueError as exc:  # invalid JSON
        raise DonkiUnavailable(f"DONKI {kind} direct host sent invalid JSON") from exc

    if not _usable_key(api_key):
        raise DonkiUnavailable(f"DONKI {kind} direct host failed ({direct_error}); no usable key")
    try:
        r = await client.get(
            f"{KEYED_BASE}/{kind}",
            params={"startDate": start.isoformat(), "endDate": end.isoformat(), "api_key": api_key},
        )
    except httpx.HTTPError as exc:
        raise DonkiUnavailable(f"DONKI {kind} key route failed: {type(exc).__name__}") from None
    if r.status_code != 200:
        raise DonkiUnavailable(f"DONKI {kind} key route: HTTP {r.status_code}")
    try:
        return DonkiResult(kind, _events(r), "api_key", fetched_at)
    except ValueError as exc:
        raise DonkiUnavailable(f"DONKI {kind} key route sent invalid JSON") from exc


async def poll_once(
    now: datetime,
    *,
    cache: DonkiCache,
    client: httpx.AsyncClient,
    settings: NasaSettings,
) -> dict[str, CachedDonki | None]:
    """Fetch the four kinds for [now - 7 days, now]; a failed kind keeps its old file."""
    end = now.astimezone(UTC).date()
    start = end - timedelta(days=POLL_WINDOW_DAYS)
    for kind in DONKI_KINDS:
        try:
            res = await donki_fetch(
                kind,
                start,
                end,
                client=client,
                base=settings.donki_base,
                api_key=settings.api_key,
                now=now,
            )
            cache.write(res)
        except DonkiUnavailable as exc:
            log.warning("DONKI %s poll failed, cache kept: %s", kind, exc)
    return {kind: cache.read(kind) for kind in DONKI_KINDS}


async def run_poller(
    stop: asyncio.Event,
    *,
    settings: NasaSettings,
    cache: DonkiCache,
    client: httpx.AsyncClient,
    clock: Callable[[], datetime],
    after_poll: Sequence[Callable[[datetime], Awaitable[None]]] = (),
    interval_s: int = POLL_INTERVAL_S,
) -> None:
    """One cycle at start, then one per interval, until stop is set. Nothing ends the loop."""
    while not stop.is_set():
        now = clock()
        if settings.donki_mode == "live":
            try:
                await poll_once(now, cache=cache, client=client, settings=settings)
            except Exception:
                log.exception("DONKI poll cycle failed")
        for cb in after_poll:
            try:
                await cb(now)
            except Exception:
                log.exception("after_poll callback failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            pass


async def _cli(kind: str, start: date, end: date, api_key: str | None, base: str) -> int:
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        res = await donki_fetch(kind, start, end, client=client, base=base, api_key=api_key)
    print(f"{kind} {start}..{end}: {len(res.events)} events via {res.route}")
    for e in res.events[:5]:
        print(" ", e.get("eventTime") or e.get("peakTime") or e.get("startTime"))
    return 0


def main(argv: list[str] | None = None) -> int:
    import os

    from hub.nasa.config import load_nasa_settings

    ap = argparse.ArgumentParser(description="Fetch DONKI events once.")
    ap.add_argument("kind")
    ap.add_argument("start", type=date.fromisoformat)
    ap.add_argument("end", type=date.fromisoformat)
    args = ap.parse_args(argv)
    s = load_nasa_settings(os.environ)
    try:
        _check(args.kind, args.start, args.end)
        return asyncio.run(_cli(args.kind, args.start, args.end, s.api_key, s.donki_base))
    except (ValueError, DonkiUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
