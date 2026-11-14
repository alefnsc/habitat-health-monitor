"""NASA gateway routes (task N4). H19 includes `router`; no network call at request time."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from hub.nasa.spaceweather import space_weather_state
from hub.nasa.state import NasaState, get_nasa_state

router = APIRouter()

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
        "ack": getattr(state.policy, "ack", None) if state.policy is not None else None,
        "disclaimer": DISCLAIMER,
    }
