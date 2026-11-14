"""HTTP app factory and core routes (H5; later tasks add status, outbox, ws, wiring)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from hub.config import Settings, load_settings
from hub.contract import CREWS, DERIVED, INDICATORS
from hub.derive import derive_ppco2
from hub.ingest import Ingestor, IngestResult
from hub.store import Store
from hub.timeutil import parse_iso

log = logging.getLogger("hub.api")

DEFAULT_LIMIT = 500
MAX_LIMIT = 5000


def reject(reason: str, status: int = 422) -> JSONResponse:
    return JSONResponse({"reason": reason}, status_code=status)


def ingest_response(res: IngestResult) -> JSONResponse:
    """D4: 201 new, 200 duplicate, 422 {reason} on contract errors. Never 409."""
    if res.reason is not None:
        return reject(res.reason, 500 if res.reason == "internal_error" else 422)
    stored = res.stored
    assert stored is not None
    body = {
        "id": stored.id,
        "measured_at": stored.measured_at,
        "duplicate": res.duplicate,
        "results": [e.to_dict() for e in res.results],
    }
    return JSONResponse(body, status_code=200 if res.duplicate else 201)


def create_app(
    settings: Settings,
    *,
    clock: Callable[[], datetime] | None = None,
    store: Store | None = None,
) -> FastAPI:
    clock = clock or (lambda: datetime.now(UTC))
    owns_store = store is None
    store = store or Store(settings.db_path)
    ingestor = Ingestor(store, clock, deriver=derive_ppco2)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if owns_store:
                store.close()

    app = FastAPI(title="Habitat hub", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.ingestor = ingestor
    app.state.clock = clock

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        err = exc.errors()[0] if exc.errors() else {}
        loc = [str(p) for p in err.get("loc", ()) if p not in ("query", "body", "path")]
        name = loc[0] if loc else "body"
        kind = "missing_field" if err.get("type") == "missing" else "bad_type"
        return reject(f"{kind}:{name}")

    @app.post("/api/readings")
    async def post_reading(request: Request) -> JSONResponse:
        body = await request.body()
        res = await run_in_threadpool(ingestor.ingest_reading, body, channel="http")
        return ingest_response(res)

    @app.post("/api/reps")
    async def post_rep(request: Request) -> JSONResponse:
        body = await request.body()
        res = await run_in_threadpool(ingestor.ingest_rep, body, channel="http")
        return ingest_response(res)

    @app.get("/api/readings")
    def get_readings(request: Request) -> JSONResponse:
        q = request.query_params
        ind = q.get("ind")
        if not ind:
            return reject("missing_field:ind")
        if ind not in INDICATORS and ind not in DERIVED:
            return reject("unknown_ind")
        since = None
        if q.get("since"):
            try:
                since = parse_iso(q["since"])
            except ValueError:
                return reject("bad_value:since")
        limit = DEFAULT_LIMIT
        if q.get("limit"):
            try:
                limit = int(q["limit"])
            except ValueError:
                return reject("bad_type:limit")
        limit = max(1, min(MAX_LIMIT, limit))
        crew = q.get("crew") or None
        if crew is not None and crew not in CREWS:
            return reject("bad_crew")
        rows = store.readings(ind, since=since, limit=limit, crew=crew)
        return JSONResponse([r.to_dict() for r in rows])

    return app


def app_factory() -> FastAPI:
    return create_app(load_settings(os.environ))
