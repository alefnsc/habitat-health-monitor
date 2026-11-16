"""GET /api/signals and GET /api/signals/{id} (D45 §4.1). Read-only: nothing is stored."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from hub.contract import CREWS
from hub.signals.catalogue import BY_ID
from hub.signals.engine import evaluate
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import to_iso

router = APIRouter()


@dataclass
class SignalsState:
    store: Store
    rules: Sequence[Rule]
    crews: Sequence[str]
    tz: str
    clock: Callable[[], datetime]


def _reject(reason: str, status: int = 422) -> JSONResponse:
    return JSONResponse({"reason": reason}, status_code=status)


def _args(request: Request) -> tuple[SignalsState, list[str], datetime] | JSONResponse:
    st: SignalsState | None = getattr(request.app.state, "signals", None)
    if st is None:
        return _reject("signals_off", 503)
    crew = request.query_params.get("crew")
    if crew is not None and crew not in CREWS:
        return _reject("bad_crew")
    raw_at = request.query_params.get("at")
    if raw_at is None:
        at = st.clock()
    else:
        try:
            at = datetime.fromisoformat(raw_at)
        except ValueError:
            return _reject("bad_value:at")
        if at.tzinfo is None:
            return _reject("bad_value:at")
    return st, [crew] if crew else list(st.crews), at


@router.get("/api/signals")
def get_signals(request: Request) -> JSONResponse:
    a = _args(request)
    if isinstance(a, JSONResponse):
        return a
    st, crews, at = a
    sigs = evaluate(st.store, st.rules, crews=crews, at=at, tz=st.tz)
    crew = request.query_params.get("crew")
    return JSONResponse({"crew": crew, "at": to_iso(at), "signals": [s.to_dict() for s in sigs]})


@router.get("/api/signals/{sid}")
def get_signal(sid: str, request: Request) -> JSONResponse:
    if sid not in BY_ID:
        return _reject("unknown_signal", 404)
    a = _args(request)
    if isinstance(a, JSONResponse):
        return a
    st, crews, at = a
    sigs = evaluate(st.store, st.rules, crews=crews, at=at, tz=st.tz, ids=[sid])
    return JSONResponse({"at": to_iso(at), "signals": [s.to_dict() for s in sigs]})
