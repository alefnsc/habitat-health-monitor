"""HTTP app factory and core routes (H5; later tasks add status, outbox, ws, wiring)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool

from hub.assess import Assessor, load_escalation, status_body
from hub.config import Settings, load_settings
from hub.contract import CREWS, DERIVED, INDICATORS, ContractError
from hub.crew import CrewRegistry, parse_badge, validate_crew_post
from hub.derive import derive_ppco2
from hub.events import EventBus
from hub.features import HubContext, load_features, wire_features
from hub.ingest import Ingestor, IngestResult
from hub.mqtt import MqttPublisher, NodeRegistry, run_subscriber
from hub.staticmount import BuildMount
from hub.store import Store
from hub.thresholds import load_rule_files
from hub.timeutil import parse_iso

log = logging.getLogger("hub.api")

DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
OUTBOX_DEFAULT = 500
OUTBOX_MAX = 1000


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
    if clock().year < 2026:
        log.warning("hub clock reads %s; set the system time before recording data", clock())
    bus = EventBus()
    nodes = NodeRegistry(clock)
    crew_registry = CrewRegistry(store, clock)
    rules = load_rule_files([settings.thresholds_path, settings.food_thresholds_path])
    assessor = Assessor(
        store,
        rules,
        tz=settings.tz,
        escalation=load_escalation(settings.guidance_path),
        emit=bus.publish,
        clock=clock,
    )
    ingestor = Ingestor(
        store,
        clock,
        emit=bus.publish,
        deriver=derive_ppco2,
        assessor=assessor,
        crew_for=crew_registry.get,
    )
    publisher = MqttPublisher()
    features = load_features(settings)

    def snapshot_frame() -> None:
        bus.publish("snapshot", status_body(store, app.state.node_states(), None, clock()))

    nodes.on_change(snapshot_frame)

    def on_badge_message(node: str, payload: bytes) -> None:
        """habitat/v1/badge/<node>: set the crew, then tell each badge handler (D11)."""
        try:
            badge = parse_badge(payload, expected_node=node)
        except ContractError as e:
            log.info("reject channel=badge reason=%s", e.reason)
            return
        crew_registry.on_badge(badge)
        for handler in app.state.runtime.badge_handlers:
            try:
                handler(node, badge.crew, clock())
            except Exception:
                log.exception("badge handler failed")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        await runtime.start(stop)
        tasks: list[asyncio.Task] = []
        bus.loop = asyncio.get_running_loop()
        if settings.mqtt_host:
            tasks.append(
                asyncio.create_task(
                    run_subscriber(
                        settings,
                        ingestor,
                        nodes,
                        stop,
                        publisher=publisher,
                        extra_subscriptions=app.state.extra_subscriptions,
                        handlers=app.state.mqtt_handlers,
                    )
                )
            )
        try:
            yield
        finally:
            await runtime.stop()
            stop.set()
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            if owns_store:
                store.close()

    app = FastAPI(title="Habitat hub", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.ingestor = ingestor
    app.state.assessor = assessor
    app.state.clock = clock
    app.state.bus = bus
    app.state.nodes = nodes
    app.state.crew = crew_registry
    app.state.publisher = publisher
    app.state.node_states = lambda: [n.to_dict() for n in nodes.snapshot()]
    app.state.features = features
    app.state.extra_subscriptions = ("habitat/v1/badge/+",)
    app.state.mqtt_handlers = {"badge": on_badge_message}
    ctx = HubContext(settings, store, ingestor, assessor, bus, nodes, crew_registry, None, clock)
    runtime = wire_features(app, features, ctx)
    app.state.runtime = runtime
    app.mount("/camera", BuildMount(settings.camera_dist, "npm --prefix camera run build"))

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

    @app.post("/api/crew")
    async def post_crew(request: Request) -> JSONResponse:
        try:
            try:
                body = json.loads(await request.body())
            except ValueError:
                raise ContractError("bad_json") from None
            node, crew = validate_crew_post(body)
        except ContractError as e:
            return reject(e.reason)
        crew_registry.set(node, crew)
        return JSONResponse({"node": node, "crew": crew})

    @app.get("/api/outbox")
    def get_outbox(request: Request) -> JSONResponse:
        q = request.query_params
        try:
            after = int(q["after"]) if q.get("after") else 0
        except ValueError:
            return reject("bad_type:after")
        if after < 0:
            return reject("bad_value:after")
        try:
            limit = int(q["limit"]) if q.get("limit") else OUTBOX_DEFAULT
        except ValueError:
            return reject("bad_type:limit")
        limit = max(1, min(OUTBOX_MAX, limit))
        items = store.outbox_after(after, limit)
        return JSONResponse(
            {
                "items": [
                    {"id": i.id, "kind": i.kind, "created_at": i.created_at, "payload": i.payload}
                    for i in items
                ],
                "last_id": items[-1].id if items else after,
            }
        )

    @app.get("/api/status")
    def get_status(request: Request) -> JSONResponse:
        crew = request.query_params.get("crew") or None
        if crew is not None and crew not in CREWS:
            return reject("bad_crew")
        return JSONResponse(status_body(store, app.state.node_states(), crew, clock()))

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        q = bus.subscribe()
        try:
            await ws.send_json(
                {
                    "type": "snapshot",
                    "data": status_body(store, app.state.node_states(), None, clock()),
                }
            )
            recv = asyncio.create_task(ws.receive_text())
            get = asyncio.create_task(q.get())
            try:
                while True:
                    done, _ = await asyncio.wait({recv, get}, return_when=asyncio.FIRST_COMPLETED)
                    if get in done:
                        item = get.result()
                        if item is None:
                            await ws.close(code=1013)
                            break
                        await ws.send_json(item)
                        get = asyncio.create_task(q.get())
                    if recv in done:
                        if recv.exception() is not None:
                            break
                        recv = asyncio.create_task(ws.receive_text())  # inbound text is ignored
            finally:
                recv.cancel()
                get.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe(q)

    _mount_static(app, settings)
    return app


def _mount_static(app: FastAPI, settings: Settings) -> None:
    """The console at `/` is the router's fallback, so it stays last however many routers
    or mounts are added after this call; unknown /api paths still answer 404."""
    console = BuildMount(settings.console_dist, "npm --prefix console run build")

    async def fallback(scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(("/api/", "/ws")):
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await console(scope, receive, send)

    app.router.default = fallback


def app_factory() -> FastAPI:
    return create_app(load_settings(os.environ))
