"""Food routes (NU6). H19 includes `router` under the `food` feature and sets `app.state.food`
to a `FoodState` (see `make_state`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from hub.food.catalog import Catalog
from hub.food.day import food_day
from hub.food.log import FoodError, FoodWriter, MealItem, MealRequest
from hub.food.references import load_references
from hub.timeutil import parse_iso

router = APIRouter()


@dataclass
class FoodState:
    catalog: Catalog
    writer: FoodWriter


def _reject(reason: str) -> JSONResponse:
    return JSONResponse({"reason": reason}, status_code=422)


def _state(request: Request) -> FoodState | None:
    return getattr(request.app.state, "food", None)


def _parse_time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise TypeError("eaten_at must be a string")
    d = datetime.fromisoformat(raw)
    if d.tzinfo is None:
        raise ValueError
    return d


def parse_meal(body: object) -> MealRequest:
    if not isinstance(body, dict):
        raise FoodError("bad_body")
    items_raw = body.get("items")
    if not isinstance(items_raw, list):
        raise FoodError("empty_meal")
    items: list[MealItem] = []
    for it in items_raw:
        if (
            not isinstance(it, dict)
            or not isinstance(it.get("food_id"), str)
            or isinstance(it.get("servings"), bool)
            or not isinstance(it.get("servings"), (int, float))
        ):
            raise FoodError("bad_item")
        items.append(MealItem(it["food_id"], float(it["servings"])))
    crew = body.get("crew")
    if crew is not None and not isinstance(crew, str):
        raise FoodError("bad_crew")
    eaten = None
    if body.get("eaten_at") is not None:
        try:
            eaten = _parse_time(body["eaten_at"])
        except (TypeError, ValueError):
            raise FoodError("bad_time") from None
    return MealRequest(crew=crew, items=items, eaten_at=eaten)


@router.get("/api/food/catalog")
def get_catalog(request: Request) -> JSONResponse:
    st = _state(request)
    if st is None:
        return JSONResponse({"reason": "food_unavailable"}, status_code=503)
    return JSONResponse(st.catalog.raw)


@router.post("/api/food/log")
async def post_log(request: Request) -> JSONResponse:
    st = _state(request)
    if st is None:
        return JSONResponse({"reason": "food_unavailable"}, status_code=503)
    try:
        body = await request.json()
    except ValueError:
        return _reject("bad_body")
    try:
        req = parse_meal(body)
        res = await run_in_threadpool(st.writer.log_meal, req)
    except FoodError as e:
        return _reject(e.reason)
    return JSONResponse(
        {
            "meal_id": res.meal_id,
            "readings": [{"ind": i, "id": rid, "duplicate": d} for i, rid, d in res.readings],
            "not_reported": res.not_reported,
            "results": [r.to_dict() for r in res.results],
        },
        status_code=201,
    )


def _ctx(request: Request):
    return getattr(request.app.state, "ctx", None)


@router.get("/api/food/references")
def get_references(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    if ctx is None:
        return JSONResponse({"reason": "food_unavailable"}, status_code=503)
    try:
        return JSONResponse(load_references(ctx.settings.food_references_path))
    except ValueError as e:
        return JSONResponse({"reason": f"references_unavailable: {e}"}, status_code=503)


@router.get("/api/food/day")
def get_day(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    if ctx is None:
        return JSONResponse({"reason": "food_unavailable"}, status_code=503)
    q = request.query_params
    crew = q.get("crew") or None
    if crew is not None and crew not in ctx.settings.crews:
        return _reject("bad_crew")
    try:
        at = parse_iso(q["at"]) if q.get("at") else request.app.state.clock()
    except ValueError:
        return _reject("bad_time")
    body = food_day(
        ctx.store, ctx.assessor, crew, at, crews=ctx.settings.crews,
        rules=getattr(ctx.assessor, "rules", []),
    )  # fmt: skip
    return JSONResponse(body)
