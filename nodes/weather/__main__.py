"""python -m nodes.weather pull [--hours N] [--hub URL] [--dry-run]: outdoor Earth reference (D45).

A separate process, like the ring importer: the habitat hub never calls the internet. Each run
fetches the last N hours for the coarse bench cell and posts them as earth-1 readings (src ref).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from nodes.ring.hubpost import post_readings
from nodes.weather.location import LocationError, coarse_location, env_file_values
from nodes.weather.mapper import map_hours
from nodes.weather.provider import Provider, default_provider

DEFAULT_HUB = "http://127.0.0.1:8000"
log = logging.getLogger("nodes.weather")


def run_pull(
    provider: Provider, *, hours: int, now: datetime, post: Callable[[list[dict]], dict] | None,
) -> dict:  # fmt: skip
    rows = provider.hours(now - timedelta(hours=hours), now)
    readings = map_hours(rows, now_ms=int(now.timestamp() * 1000))
    counts = {"hours": len(rows), "readings": len(readings)}
    if post is not None:
        counts.update(post(readings))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nodes.weather")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull", help="fetch the last N hours and post them to the hub")
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--hub", default=os.environ.get("WEATHER_HUB", DEFAULT_HUB))
    p.add_argument("--dry-run", action="store_true", help="fetch and map, post nothing")
    a = ap.parse_args(argv)
    try:
        lat, lon = coarse_location(os.environ, env_file_values(Path(".env")))
    except LocationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    provider = default_provider(lat, lon)
    now = datetime.now(UTC)
    if a.dry_run:
        counts = run_pull(provider, hours=a.hours, now=now, post=None)
    else:
        with httpx.Client(base_url=a.hub, timeout=10) as http:
            counts = run_pull(provider, hours=a.hours, now=now,
                              post=lambda rs: post_readings(rs, http))  # fmt: skip
    print(" ".join(f"{k}={v}" for k, v in counts.items()))  # counts only: never the location
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
