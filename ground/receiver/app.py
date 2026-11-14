"""Ground receiver HTTP app: ingest, arrivals, summary, static ground page."""

from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import store


class OutboxItemBody(BaseModel):
    id: int
    kind: Literal["reading", "rep", "alert", "prompt_answer"]
    created_at: str
    payload: dict[str, Any]


class IngestBody(BaseModel):
    beacon: dict[str, Any] | None = None
    items: list[OutboxItemBody]


def create_app(db_path: Path, static_dir: Path | None) -> FastAPI:
    conn = store.open_db(db_path)
    lock = threading.Lock()
    app = FastAPI(title="Ground receiver")

    @app.post("/ground/ingest")
    def post_ingest(body: IngestBody) -> dict[str, int | None]:
        received_at = store.utc_now()
        with lock:
            res = store.ingest(
                conn, body.beacon, [i.model_dump() for i in body.items], received_at
            )
        return {"max_id": res.max_id, "stored": res.stored}

    @app.get("/ground/arrivals")
    def get_arrivals(
        after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000)
    ) -> list[dict[str, Any]]:
        with lock:
            rows = store.arrivals_after(conn, after, limit)
        return [asdict(r) for r in rows]

    @app.get("/ground/summary")
    def get_summary() -> dict[str, Any]:
        with lock:
            return asdict(store.summary(conn))

    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app
