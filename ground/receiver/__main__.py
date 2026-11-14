"""Run the ground receiver: python -m receiver --db receiver/var/ground.db --static dist"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="receiver")
    p.add_argument("--db", type=Path, default=Path("receiver/var/ground.db"))
    p.add_argument("--static", type=Path, default=None)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8100)
    args = p.parse_args()
    uvicorn.run(create_app(args.db, args.static), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
