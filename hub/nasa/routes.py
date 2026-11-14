"""NASA gateway routes (task N4). H19 includes `router`; no network call at request time."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hub.nasa.actuator import NoActiveAlert
from hub.nasa.spaceweather import space_weather_state
from hub.nasa.state import NasaState, get_nasa_state

router = APIRouter()
log = logging.getLogger(__name__)
_snapshot_cache: dict[Path, tuple[tuple[int, int], dict]] = {}

DISCLAIMER = (
    "DONKI is a research-grade archive from NASA CCMC and may lag real events. "
    "NOAA SWPC is the official space-weather forecast source."
)


def _z(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/api/nasa/space-weather")
def get_space_weather(state: NasaState = Depends(get_nasa_state)) -> dict[str, Any]:  # noqa: B008
    st = space_weather_state(state.clock(), settings=state.settings, cache=state.cache)
    a = st.alert
    return {
        "status": a.status,
        "rule_id": a.rule_id,
        "reason": a.reason,
        "event_id": a.event_id,
        "event_time": _z(a.event_time),
        "link": a.link,
        "mode": st.mode,
        "cached_at": _z(st.cached_at),
        "stale": st.stale,
        "route": st.route,
        "events": st.events,
        "ack": _ack_body(getattr(state.policy, "ack", None)),
        "disclaimer": DISCLAIMER,
    }


def _read_snapshot(path: Path) -> dict | None:
    """Read the committed OSDR snapshot, again only when the file changes. No network."""
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
        hit = _snapshot_cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise TypeError("snapshot is not an object")
        _snapshot_cache[path] = (key, data)
        return data
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as exc:
        log.warning("OSDR snapshot %s unreadable: %s", path, exc)
        return None


@router.get("/api/nasa/iss-reference", response_model=None)
def get_iss_reference(state: NasaState = Depends(get_nasa_state)) -> Any:  # noqa: B008
    snap = _read_snapshot(state.settings.osdr_snapshot_path)
    writer = state.dose
    est = getattr(writer, "last", None)
    if snap is None and est is None:
        return JSONResponse({"reason": "no_reference_data"}, status_code=503)

    cabin = None
    absorbed = per_day = None
    if snap is not None:
        c = snap.get("cabin") or {}
        cabin = {
            "temperature_c": c.get("temperature_c"),
            "rh_pct": c.get("rh_pct"),
            "co2_mmhg": c.get("co2_mmhg"),
            "co2_raw": c.get("co2_raw"),
            "co2_raw_unit": c.get("co2_raw_unit"),
        }
        d = snap.get("dose") or {}
        absorbed, per_day = d.get("absorbed_mgy"), d.get("absorbed_mgy_per_day")
    return {
        "snapshot_date": snap.get("fetched_at") if snap else None,
        "mission": snap.get("mission") if snap else None,
        "source_urls": snap.get("source_urls", []) if snap else [],
        "label": "snapshot",
        "cabin": cabin,
        "dose": {
            "absorbed_mgy": absorbed,
            "absorbed_mgy_per_day": per_day,
            "effective_msv": est.effective_msv if est else None,
            "effective_msv_method": est.effective_msv_method if est else None,
            "status": getattr(writer, "last_status", "unknown") if est else "unknown",
            "profile": est.profile if est else None,
            "mission_day": est.mission_day if est else None,
            "career_limit_msv": est.career_limit_msv if est else None,
            "career_fraction": est.career_fraction if est else None,
        },
    }


def _ack_body(ack: Any) -> Any:
    if ack is None or isinstance(ack, dict):
        return ack
    return {"crew": ack.crew, "at": _z(ack.at), "event_id": ack.event_id}


class AckRequest(BaseModel):
    crew: str


@router.post("/api/nasa/space-weather/ack", response_model=None)
def post_space_weather_ack(body: AckRequest, state: NasaState = Depends(get_nasa_state)) -> Any:  # noqa: B008
    if body.crew not in state.crews:
        raise HTTPException(status_code=422, detail="unknown crew")
    policy = state.policy
    try:
        if policy is None:
            raise NoActiveAlert
        ack = policy.acknowledge(body.crew, state.clock())
    except NoActiveAlert:
        return JSONResponse({"reason": "no_active_alert"}, status_code=409)
    return {"ack": _ack_body(ack)}
