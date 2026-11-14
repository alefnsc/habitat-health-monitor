"""Run the link simulator.

python -m linksim --config linksim/link.json --hub http://127.0.0.1:8000 \
  --ground http://<earth-ip>:8100 --state linksim/var/state.json
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import load_config
from .consent import parse_crews
from .engine import LinkEngine
from .io import load_cursor, step
from .public import PublicUplink
from .status import serve_status

TICK_S = 0.25


def wall(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def public_banner(crews: frozenset[str], reps: bool) -> str:
    return f"public crews: {','.join(sorted(crews)) or 'none'}; reps public: {'yes' if reps else 'no'}"


def main() -> None:
    p = argparse.ArgumentParser(prog="linksim")
    p.add_argument("--config", type=Path, default=Path("linksim/link.json"))
    p.add_argument("--hub", default="http://127.0.0.1:8000")
    p.add_argument(
        "--ground", default="http://127.0.0.1:8100", help="empty string = no local receiver"
    )
    p.add_argument("--public-ground", default=os.environ.get("PUBLIC_GROUND_URL", ""))
    p.add_argument("--public-crews", default=os.environ.get("PUBLIC_CREWS", ""))
    p.add_argument(
        "--public-reps", action="store_true", default=os.environ.get("PUBLIC_REPS", "") == "1"
    )
    p.add_argument(
        "--public-flush-s", type=float, default=float(os.environ.get("PUBLIC_FLUSH_S") or "10")
    )
    p.add_argument("--state", type=Path, default=Path("linksim/var/state.json"))
    p.add_argument("--status-host", default="127.0.0.1")
    p.add_argument("--status-port", type=int, default=8200)
    args = p.parse_args()

    cfg = load_config(args.config)
    engine = LinkEngine(cfg, time.time(), wall)
    engine.fetched_id = load_cursor(args.state)
    serve_status(engine, args.status_host, args.status_port, time.time)

    hub = httpx.Client(base_url=args.hub, timeout=3.0)
    ground = httpx.Client(base_url=args.ground, timeout=3.0) if args.ground else None
    public = None
    if args.public_ground:
        secret = os.environ.get("GROUND_INGEST_SECRET", "")
        if not secret:
            raise SystemExit("GROUND_INGEST_SECRET is required when --public-ground is set")
        crews = parse_crews(args.public_crews)
        public = PublicUplink(
            httpx.Client(base_url=args.public_ground, timeout=2.0),
            secret,
            crews,
            args.public_reps,
            args.public_flush_s,
        )
        print(
            "public uplink ON: items from node sim-1 are published as synthetic; "
            "never replay recordings of real people through sim-1 while it is on",
            flush=True,
        )
        print(public_banner(crews, args.public_reps), flush=True)
    last_poll = last_line = 0.0
    while True:
        now = time.time()
        poll = now - last_poll >= 1.0
        if poll:
            last_poll = now
        step(engine, hub, ground, args.state, now, poll=poll, public=public)
        if now - last_line >= 1.0:
            last_line = now
            snap, d = engine.snapshot(now), engine.detail(now)
            print(
                f"state={snap.state} hold={d.hold_s:.1f}s queue_len={snap.queue_len} "
                f"in_flight={d.in_flight} fetched={d.fetched_id} delivered={d.delivered_id} "
                f"pub_delivered={public.delivered_id if public else '-'} "
                f"pub_queue={len(public.queue) if public else '-'}",
                flush=True,
            )
        time.sleep(TICK_S)


if __name__ == "__main__":
    main()
