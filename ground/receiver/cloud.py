"""Public ground segment app: the local receiver's API on a RedisStore, with signed writes (D38)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from pydantic import ValidationError

from .app import IngestBody
from .redis_store import RedisStore
from .signing import HEADER, verify
from .store import utc_now

CACHE = "public, max-age=0, s-maxage=5, stale-while-revalidate=30"
# The hosting function refuses responses over 4.5 MB; stay well under it.
MAX_RESPONSE_BYTES = 2_500_000


def within_budget(arrivals: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Leading arrivals whose JSON list fits in `budget` bytes (always at least one).

    The client pages on from the last arrival_id until an empty page, so a cut page loses nothing.
    """
    out: list[dict[str, Any]] = []
    size = 2  # the list brackets
    for a in arrivals:
        n = len(json.dumps(a, ensure_ascii=False, separators=(",", ":")).encode()) + (1 if out else 0)
        if out and size + n > budget:
            break
        out.append(a)
        size += n
    return out


def create_cloud_app(
    store: RedisStore,
    secret: str,
    max_body: int = 1_000_000,
    max_items: int = 1000,
    max_response: int = MAX_RESPONSE_BYTES,
) -> FastAPI:
    app = FastAPI(title="Ground segment (public)")
    router = APIRouter()

    async def signed_body(request: Request) -> bytes:
        body = await request.body()
        if len(body) > max_body:
            raise HTTPException(413, "body too large")
        if not verify(body, request.headers.get(HEADER), secret):
            raise HTTPException(401, "bad signature")
        return body

    @router.post("/ground/ingest")
    async def ingest(request: Request) -> dict[str, int | None]:
        body = await signed_body(request)
        try:
            parsed = IngestBody.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(422, "bad body") from exc
        if len(parsed.items) > max_items:
            raise HTTPException(413, "too many items")
        res = store.ingest(parsed.beacon, [i.model_dump() for i in parsed.items], utc_now())
        return {"max_id": res.max_id, "stored": res.stored}

    @router.get("/ground/arrivals")
    def arrivals(
        response: Response,
        after: int = Query(0, ge=0),
        limit: int = Query(500, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        response.headers["Cache-Control"] = CACHE
        return within_budget([asdict(a) for a in store.arrivals_after(after, limit)], max_response)

    @router.get("/ground/summary")
    def summary(response: Response) -> dict[str, Any]:
        response.headers["Cache-Control"] = CACHE
        return asdict(store.summary())

    @router.post("/ground/purge")
    async def purge(request: Request) -> dict[str, int]:
        body = await signed_body(request)
        try:
            crew = json.loads(body)["crew"]
            if not isinstance(crew, str) or not crew:
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, "body must be {\"crew\": \"<id>\"}") from exc
        return {"removed": store.purge_crew(crew)}

    app.include_router(router)
    app.include_router(router, prefix="/api")
    return app
