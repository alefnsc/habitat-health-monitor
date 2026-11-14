"""POST contract-v1 readings to the hub, one at a time, in the order given (D41 §4)."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("nodes.ring")


def post_readings(readings: list[dict], http: httpx.Client) -> dict[str, int]:
    """Counts of stored (201), duplicate (200) and rejected (anything else) readings.

    `http` carries the hub's base URL. Connection errors propagate: the hub is local and
    must be up, and a partial replay is safe to repeat because the hub dedupes.
    """
    counts = {"stored": 0, "duplicate": 0, "rejected": 0}
    for r in readings:
        res = http.post("/api/readings", json=r)
        if res.status_code == 201:
            counts["stored"] += 1
        elif res.status_code == 200:
            counts["duplicate"] += 1
        else:
            counts["rejected"] += 1
            log.warning("rejected seq=%s ind=%s: %s %s", r.get("seq"), r.get("ind"),
                        res.status_code, res.text[:200])  # fmt: skip
    return counts
