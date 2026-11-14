"""GET /api/nasa/iss-cabin (N9, body canonical per D18). Included by hub.nasa.routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from hub.nasa.isslive import ISS_ITEMS, iss_timestamp_to_utc
from hub.nasa.state import NasaState, get_nasa_state

router = APIRouter()

LIVE_GRACE = timedelta(seconds=120)
STALE_AFTER_S = 600
MMHG_TO_HPA = 1.333224
UNIT_NOTE = (
    "The feed labels cabin pressure in PSI, but the values are mmHg by magnitude "
    "(about 760). Temperature is in degrees Celsius."
)
UNITS = {
    "cabin_pressure": "mmHg",
    "cabin_temperature": "C",
    "lab_ppco2": "mmHg",
    "node3_ppco2": "mmHg",
}
_capture_cache: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}


def _z(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_capture(path: Path) -> dict[str, dict[str, Any]]:
    """Last line per item. Read once per file version, not per request."""
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _capture_cache:
        last: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                last[d["item"]] = d
            except (ValueError, KeyError, TypeError):
                continue
        _capture_cache[key] = last
    return _capture_cache[key]


def _row(item: str, val: float, measured: datetime, now: datetime) -> dict[str, Any]:
    name = ISS_ITEMS[item]
    unit = UNITS[name]
    age = max(0, round((now - measured).total_seconds()))
    return {
        "item": item,
        "name": name,
        "val": val,
        "unit": unit,
        "val_hpa": round(val * MMHG_TO_HPA, 2) if unit == "mmHg" else None,
        "measured_at": _z(measured),
        "age_s": age,
        "stale": age > STALE_AFTER_S,
    }


@router.get("/api/nasa/iss-cabin")
def get_iss_cabin(state: NasaState = Depends(get_nasa_state)):  # noqa: B008
    now = state.clock().astimezone(UTC)
    iss = state.iss
    live = iss.latest() if iss is not None else {}
    live = {k: v for k, v in live.items() if k in ISS_ITEMS}
    is_live = bool(live) and iss is not None and (
        iss.connected
        or (iss.last_connected_at is not None and now - iss.last_connected_at <= LIVE_GRACE)
    )
    if is_live:
        rows = [_row(k, u.val, u.measured_at, now) for k, u in live.items()]
        return {"mode": "live", "recorded_at": None, "unit_note": UNIT_NOTE, "items": rows}

    cap = _load_capture(state.settings.isslive_capture)
    rows, recorded = [], []
    for item, d in cap.items():
        if item not in ISS_ITEMS:
            continue
        received = datetime.fromisoformat(d["received_at"])
        rows.append(_row(item, float(d["val"]), iss_timestamp_to_utc(float(d["ts"]), received), now))
        recorded.append(received)
    if not rows:
        return JSONResponse({"reason": "no_iss_data"}, status_code=503)
    return {
        "mode": "recorded",
        "recorded_at": _z(max(recorded)),
        "unit_note": UNIT_NOTE,
        "items": rows,
    }
