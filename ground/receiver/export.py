"""Export a window of the receiver database as a ground replay file.

python -m receiver.export --db <path> --out <path> [--since <iso>] [--until <iso>] --label <text>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import store

DEFAULT_LIGHT_TIME_S = 720
DEFAULT_TIME_SCALE = 60


def _norm(iso: str | None) -> str | None:
    """Normalise to the stored `YYYY-MM-DDTHH:MM:SS.mmmZ` form so string compare works."""
    if iso is None:
        return None
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def export_replay(
    conn: sqlite3.Connection, since: str | None, until: str | None, label: str
) -> dict[str, Any]:
    """Read-only. Raises ValueError when the window holds no arrivals."""
    lo, hi = _norm(since), _norm(until)
    rows = store.arrivals_after(conn, 0, 10**9)
    rows = [r for r in rows if (lo is None or r.received_at >= lo) and (hi is None or r.received_at <= hi)]
    if not rows:
        raise ValueError("no arrivals in window")
    t0 = rows[0].received_at
    first = next((r.beacon for r in rows if r.beacon and "link" in r.beacon), None)
    if first:
        light, scale = first["link"]["light_time_s"], first["link"]["time_scale"]
    else:
        light, scale = DEFAULT_LIGHT_TIME_S, DEFAULT_TIME_SCALE
        label += " (link parameters assumed)"
    return {
        "v": 1,
        "kind": "ground-replay",
        "label": label,
        "exported_at": store.utc_now(),
        "t0": t0,
        "light_time_s": light,
        "time_scale": scale,
        "arrivals": [
            {"at_ms": _ms(r.received_at) - _ms(t0), "beacon": r.beacon, "items": r.items}
            for r in rows
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(prog="receiver.export")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--label", required=True)
    args = p.parse_args()
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        replay = export_replay(conn, args.since, args.until, args.label)
    except ValueError as exc:
        print(exc)
        sys.exit(1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(replay, ensure_ascii=False))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
