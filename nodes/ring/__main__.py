"""python -m nodes.ring {replay,auth,pull}: the wearable ring importer (D41).

  replay FILE [--hub URL]   post recorded pulls as src replay (no cloud access)
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import httpx

from nodes.ring.hubpost import post_readings
from nodes.ring.mapper import map_pull
from nodes.ring.records import load_records

DEFAULT_HUB = "http://127.0.0.1:8000"


def _report(verb: str, n: int, counts: dict[str, int], skipped: Counter[str]) -> None:
    print(
        f"{verb} {n} record(s): stored {counts['stored']}, duplicate {counts['duplicate']}, "
        f"rejected {counts['rejected']}"
    )
    if skipped:
        print("skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(skipped.items())))


def _replay(args: argparse.Namespace, http: httpx.Client) -> int:
    records = load_records(Path(args.file))
    totals = {"stored": 0, "duplicate": 0, "rejected": 0}
    skipped: Counter[str] = Counter()
    for rec in records:
        res = map_pull(rec, mode="replay")
        skipped.update(res.skipped)
        for k, v in post_readings(res.readings, http).items():
            totals[k] += v
    _report("replayed", len(records), totals, skipped)
    return 0 if totals["rejected"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m nodes.ring", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("replay", help="post recorded pulls as src replay")
    rp.add_argument("file", help="a pulls JSONL file, such as data/replay/ring-synthetic-nights.jsonl")
    rp.add_argument("--hub", default=DEFAULT_HUB, help=f"hub base URL (default {DEFAULT_HUB})")
    return ap


def main(argv: list[str] | None = None, *, http: httpx.Client | None = None) -> int:
    args = build_parser().parse_args(argv)
    if http is None:
        with httpx.Client(base_url=args.hub, timeout=10) as client:
            return main(argv, http=client)
    if args.cmd == "replay":
        return _replay(args, http)
    return 2


if __name__ == "__main__":
    sys.exit(main())
