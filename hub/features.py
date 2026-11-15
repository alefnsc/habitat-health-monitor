"""Feature-gated wiring of the optional modules (D10, D14, NU14).

Every feature module is imported under a guard: a cut or broken task lands in
`Features.skipped` with its reason and never stops the hub from starting.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import date, datetime
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI

from hub.assess import Assessor
from hub.config import Settings
from hub.crew import CrewRegistry
from hub.events import EventBus
from hub.ingest import Ingestor
from hub.mqtt import NodeRegistry
from hub.store import Store

log = logging.getLogger("hub.features")


@dataclass
class HubContext:
    settings: Settings
    store: Store
    ingestor: Ingestor
    assessor: Assessor
    bus: EventBus
    nodes: NodeRegistry
    crew: CrewRegistry
    commands: Any | None
    clock: Callable[[], datetime]


# group key -> (modules with the names that must exist on each)
_TABLE: dict[str, dict[str, tuple[str, ...]]] = {
    "nasa": {
        "hub.nasa.config": ("load_nasa_settings",),
        "hub.nasa.donki_cache": ("DonkiCache",),
        "hub.nasa.donki": ("run_poller",),
        "hub.nasa.state": ("NasaState",),
        "hub.nasa.routes": ("router",),
    },
    "nasa.actuator": {"hub.nasa.actuator": ("ActuatorPolicy",)},
    "nasa.dose": {"hub.nasa.dose": ("load_dose_profile", "DoseWriter")},
    "iss": {
        "hub.nasa.isslive": ("IssLiveState", "ISS_ITEMS"),
        "hub.nasa.isslive_client": ("IssLiveClient",),
    },
    "wearable": {"hub.wearable.routes": ("WearableState", "router")},
    "mcp": {"hub.mcp_server": ("build_mcp",)},
    "food": {
        "hub.food.catalog": ("load_catalog", "CatalogError"),
        "hub.food.log": ("FoodWriter",),
        "hub.food.routes": ("router",),
    },
    "signals": {
        "hub.signals.engine": ("evaluate",),
        "hub.signals.routes": ("router", "SignalsState"),
    },
}


@dataclass
class Features:
    loaded: dict[str, ModuleType] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)

    def mod(self, name: str) -> Any:
        return self.loaded[name]


def _import_group(group: dict[str, tuple[str, ...]]) -> dict[str, ModuleType]:
    out: dict[str, ModuleType] = {}
    for name, needed in group.items():
        mod = importlib.import_module(name)
        missing = [n for n in needed if not hasattr(mod, n)]
        if missing:
            raise ImportError(f"{name} has no {', '.join(missing)}")
        out[name] = mod
    return out


def load_features(settings: Settings) -> Features:
    feats = Features()
    for feature in sorted(settings.features):
        groups = [feature]
        if feature == "nasa":
            groups += ["nasa.actuator", "nasa.dose"]
        for g in groups:
            if g not in _TABLE:
                continue  # ble and serial have no in-process module
            try:
                feats.loaded.update(_import_group(_TABLE[g]))
            except Exception as e:  # noqa: BLE001 - any failure disables only this feature
                feats.skipped[g] = f"{type(e).__name__}: {e}"
                log.warning("feature %s skipped: %s", g, feats.skipped[g])
    return feats


@dataclass
class FeatureRuntime:
    nasa: Any | None = None
    iss_client: Any | None = None
    mcp: Any | None = None
    wearable: Any | None = None
    badge_handlers: list[Callable[[str, str, datetime], object]] = field(default_factory=list)
    _poller: Any | None = None  # (coroutine factory) built by wire_features
    _client: httpx.AsyncClient | None = None
    _task: asyncio.Task | None = None
    _stop: asyncio.Event | None = None
    _stack: AsyncExitStack | None = None

    async def start(self, stop: asyncio.Event) -> None:
        self._stop = stop
        if self._poller is not None:
            try:
                self._client = httpx.AsyncClient()
                self._task = asyncio.create_task(self._poller(stop, self._client))
            except Exception:
                log.exception("nasa poller failed to start")
        if self.iss_client is not None:
            try:
                r = self.iss_client.start()
                if inspect.isawaitable(r):
                    await r
            except Exception:
                log.exception("iss client failed to start")
        if self.mcp is not None:
            self._stack = AsyncExitStack()
            try:
                await self._stack.enter_async_context(self.mcp.lifespan())
            except Exception:
                log.exception("mcp lifespan failed to start")
                self._stack = None

    async def stop(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                log.exception("mcp lifespan failed to stop")
        if self.iss_client is not None:
            try:
                r = self.iss_client.stop()
                if inspect.isawaitable(r):
                    await r
            except Exception:
                log.exception("iss client failed to stop")
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except BaseException:
                self._task.cancel()
                log.exception("nasa poller did not stop cleanly")
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                log.exception("http client failed to close")


def _guard(
    feats: Features, name: str, fn: Callable[[], None], level: int = logging.WARNING
) -> bool:
    try:
        fn()
        return True
    except Exception as e:
        feats.skipped[name] = f"{type(e).__name__}: {e}"
        log.log(level, "feature %s skipped: %s", name, feats.skipped[name], exc_info=True)
        return False


def wire_features(app: FastAPI, features: Features, ctx: HubContext) -> FeatureRuntime:
    app.state.ctx = ctx
    app.state.settings = ctx.settings
    settings = ctx.settings
    rt = FeatureRuntime()
    crews = tuple(settings.crews)
    on = settings.features
    f = features
    built: dict[str, Any] = {}

    def build_nasa() -> None:
        m = f.mod
        nasa_settings = m("hub.nasa.config").load_nasa_settings(os.environ)
        cache = m("hub.nasa.donki_cache").DonkiCache(nasa_settings.var_dir / "nasa")
        policy = dose = None
        if "hub.nasa.actuator" in f.loaded:
            policy = m("hub.nasa.actuator").ActuatorPolicy(
                ctx.commands, ctx.ingestor, settings=nasa_settings, cache=cache, crews=crews
            )
        if "hub.nasa.dose" in f.loaded:
            dmod = m("hub.nasa.dose")
            dose = dmod.DoseWriter(
                dmod.load_dose_profile(nasa_settings.dose_profile_path), ctx.ingestor
            )
        state = m("hub.nasa.state").NasaState(
            nasa_settings, cache, ctx.clock, crews, policy=policy, iss=None, dose=dose
        )
        app.state.nasa = state
        app.include_router(m("hub.nasa.routes").router)
        after_poll = [x.tick for x in (policy, dose) if x is not None]
        run_poller = m("hub.nasa.donki").run_poller

        def poller(stop: asyncio.Event, client: httpx.AsyncClient):
            return run_poller(
                stop, settings=nasa_settings, cache=cache, client=client, clock=ctx.clock,
                after_poll=after_poll,
            )  # fmt: skip

        rt._poller = poller
        rt.nasa = state
        built["policy"] = policy
        if policy is not None:
            rt.badge_handlers.append(policy.on_badge)

    if "nasa" in on:
        if "nasa" not in f.skipped:
            _guard(f, "nasa", build_nasa)
        for part in ("nasa.actuator", "nasa.dose"):
            pass  # their skip reasons are already recorded by load_features

    def build_iss() -> None:
        if rt.nasa is None:
            raise RuntimeError("needs nasa")
        m = f.mod
        state = m("hub.nasa.isslive").IssLiveState()
        rt.iss_client = m("hub.nasa.isslive_client").IssLiveClient(
            list(m("hub.nasa.isslive").ISS_ITEMS), state
        )
        rt.nasa.iss = state

    if "iss" in on and "iss" not in f.skipped:
        if rt.nasa is None:
            f.skipped["iss"] = "needs nasa"
            log.warning("feature iss skipped: needs nasa")
        else:
            _guard(f, "iss", build_iss)

    def build_mcp() -> None:
        m = f.mod("hub.mcp_server").build_mcp(app)
        app.mount("/mcp", m.asgi)
        rt.mcp = m

    if "mcp" in on and "mcp" not in f.skipped:
        _guard(f, "mcp", build_mcp)

    def build_wearable() -> None:
        tz = ZoneInfo(settings.tz)

        def today() -> date:
            return ctx.clock().astimezone(tz).date()

        w = f.mod("hub.wearable.routes")
        state = w.WearableState(settings.db_path, crews, today)
        app.state.wearable = state
        app.include_router(w.router)
        rt.wearable = state

    if "wearable" in on and "wearable" not in f.skipped:
        _guard(f, "wearable", build_wearable)

    def build_food() -> None:
        catalog = f.mod("hub.food.catalog").load_catalog(settings.food_catalog_path)
        boot = int(ctx.clock().timestamp())
        writer = f.mod("hub.food.log").FoodWriter(
            ctx.store, ctx.ingestor, catalog, ctx.clock, boot=boot
        )
        routes = f.mod("hub.food.routes")
        app.state.food_catalog = catalog
        app.state.food_writer = writer
        state_cls = getattr(routes, "FoodState", None)
        if state_cls is not None:
            app.state.food = state_cls(catalog, writer)
        app.include_router(routes.router)

    if "food" in on and "food" not in f.skipped:
        _guard(f, "food", build_food, level=logging.ERROR)

    def build_signals() -> None:
        routes = f.mod("hub.signals.routes")
        app.state.signals = routes.SignalsState(
            ctx.store, ctx.assessor.rules, crews, settings.tz, ctx.clock
        )
        app.include_router(routes.router)

    if "signals" in on and "signals" not in f.skipped:
        _guard(f, "signals", build_signals)

    return rt
