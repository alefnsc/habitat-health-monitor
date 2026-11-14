"""Run the link simulator.

python -m linksim --config linksim/link.json --hub http://127.0.0.1:8000 \
  --ground http://<earth-ip>:8100 --state linksim/var/state.json
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import load_config
from .engine import LinkEngine
from .io import load_cursor, step
from .status import serve_status

TICK_S = 0.25


def wall(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> None:
    p = argparse.ArgumentParser(prog="linksim")
    p.add_argument("--config", type=Path, default=Path("linksim/link.json"))
    p.add_argument("--hub", default="http://127.0.0.1:8000")
    p.add_argument("--ground", default="http://127.0.0.1:8100")
    p.add_argument("--state", type=Path, default=Path("linksim/var/state.json"))
    p.add_argument("--status-host", default="127.0.0.1")
    p.add_argument("--status-port", type=int, default=8200)
    args = p.parse_args()

    cfg = load_config(args.config)
    engine = LinkEngine(cfg, time.time(), wall)
    engine.fetched_id = load_cursor(args.state)
    serve_status(engine, args.status_host, args.status_port, time.time)

    hub = httpx.Client(base_url=args.hub, timeout=3.0)
    ground = httpx.Client(base_url=args.ground, timeout=3.0)
    last_poll = last_line = 0.0
    while True:
        now = time.time()
        poll = now - last_poll >= 1.0
        if poll:
            last_poll = now
        step(engine, hub, ground, args.state, now, poll=poll)
        if now - last_line >= 1.0:
            last_line = now
            snap, d = engine.snapshot(now), engine.detail(now)
            print(
                f"state={snap.state} hold={d.hold_s:.1f}s queue_len={snap.queue_len} "
                f"in_flight={d.in_flight} fetched={d.fetched_id} delivered={d.delivered_id}",
                flush=True,
            )
        time.sleep(TICK_S)


if __name__ == "__main__":
    main()
