import json
import logging
import sys
import types
from dataclasses import replace

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.commands import CommandRouter
from hub.config import FEATURE_NAMES
from hub.features import HubContext
from hub.tests.helpers import FOOD_RULES, MAIN_RULES

CALLS: dict[str, list] = {}


def rec(name, *a, **k):
    CALLS.setdefault(name, []).append((a, k))


def mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


class Stub:
    def __init__(self, name):
        self.name = name

    def __call__(self, *a, **k):
        rec(self.name, *a, **k)
        o = types.SimpleNamespace(args=a, kwargs=k)
        return o


def build_stubs(tmp_path, *, actuator=True, dose=True):
    CALLS.clear()
    nasa_router = APIRouter()
    nasa_router.get("/api/nasa/ping")(lambda: {"pong": True})
    food_router = APIRouter()
    food_router.get("/api/food/ping")(lambda: {"pong": True})

    @food_router.get("/api/food/ctx-check")
    def ctx_check(request: Request):
        c = request.app.state.ctx
        return {
            "store": c.store is request.app.state.store,
            "assessor": c.assessor is request.app.state.assessor,
            "tz": c.settings.tz,
        }

    ns = types.SimpleNamespace(var_dir=tmp_path, dose_profile_path=tmp_path / "dose_profile.json")
    stopped = []

    async def run_poller(stop, **kw):
        rec("run_poller", stop, **kw)
        await stop.wait()
        stopped.append(True)

    class Policy:
        def __init__(self, *a, **k):
            rec("ActuatorPolicy", *a, **k)

        def tick(self, now):
            pass

        def on_badge(self, node, crew, now):
            rec("on_badge", node, crew, now)

    class Dose:
        def __init__(self, *a, **k):
            rec("DoseWriter", *a, **k)

        def tick(self, now):
            pass

    class NasaState:
        def __init__(self, *a, **k):
            rec("NasaState", *a, **k)
            self.policy, self.dose, self.iss = k.get("policy"), k.get("dose"), k.get("iss")

    class IssClient:
        def __init__(self, *a, **k):
            rec("IssLiveClient", *a, **k)

        def start(self):
            rec("iss_start")

        def stop(self):
            rec("iss_stop")

    class McpMount:
        async def asgi(self, scope, receive, send):
            from starlette.responses import PlainTextResponse

            await PlainTextResponse("mcp-stub")(scope, receive, send)

        def lifespan(self):
            import contextlib

            @contextlib.asynccontextmanager
            async def cm():
                rec("mcp_enter")
                yield
                rec("mcp_exit")

            return cm()

    def build_mcp(app):
        rec("build_mcp", app)
        return McpMount()

    class CatalogError(Exception):
        pass

    mods = {
        "hub.nasa.config": mod("hub.nasa.config", load_nasa_settings=lambda env: ns),
        "hub.nasa.donki_cache": mod("hub.nasa.donki_cache", DonkiCache=Stub("DonkiCache")),
        "hub.nasa.donki": mod("hub.nasa.donki", run_poller=run_poller),
        "hub.nasa.state": mod("hub.nasa.state", NasaState=NasaState),
        "hub.nasa.routes": mod("hub.nasa.routes", router=nasa_router),
        "hub.nasa.isslive": mod(
            "hub.nasa.isslive",
            IssLiveState=Stub("IssLiveState"),
            ISS_ITEMS={"ITEM_A": "a", "ITEM_B": "b"},
        ),
        "hub.nasa.isslive_client": mod("hub.nasa.isslive_client", IssLiveClient=IssClient),
        "hub.wearable.routes": mod(
            "hub.wearable.routes", WearableState=Stub("WearableState"), router=APIRouter()
        ),
        "hub.mcp_server": mod("hub.mcp_server", build_mcp=build_mcp),
        "hub.food.catalog": mod(
            "hub.food.catalog", load_catalog=Stub("load_catalog"), CatalogError=CatalogError
        ),
        "hub.food.log": mod("hub.food.log", FoodWriter=Stub("FoodWriter")),
        "hub.food.routes": mod("hub.food.routes", router=food_router),
    }
    if actuator:
        mods["hub.nasa.actuator"] = mod("hub.nasa.actuator", ActuatorPolicy=Policy)
    if dose:
        mods["hub.nasa.dose"] = mod("hub.nasa.dose", load_dose_profile=Stub("load_dose_profile"),
                                    DoseWriter=Dose)  # fmt: skip
    return mods, stopped, CatalogError


@pytest.fixture
def stub_n(monkeypatch, tmp_path):
    mods, stopped, err = build_stubs(tmp_path)
    for k in ("hub.nasa.actuator", "hub.nasa.dose", *mods):
        monkeypatch.delitem(sys.modules, k, raising=False)
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    return types.SimpleNamespace(mods=mods, stopped=stopped, CatalogError=err)


def make(settings, clock, features, **kw):
    s = replace(settings, features=frozenset(features), **kw)
    return create_app(s, clock=clock)


ALL = set(FEATURE_NAMES)


def test_app_state_ctx(settings, clock, monkeypatch):
    for k in list(sys.modules):
        if k.startswith(("hub.nasa", "hub.wearable", "hub.mcp_server")):
            monkeypatch.setitem(sys.modules, k, None)
    for feats in (set(), {"serial"}, ALL):
        app = make(settings, clock, feats)
        c = app.state.ctx
        assert isinstance(c, HubContext)
        assert c.settings is app.state.settings is app.state.ctx.settings
        assert (c.store, c.ingestor, c.assessor) == (
            app.state.store, app.state.ingestor, app.state.assessor,
        )  # fmt: skip
        assert c.clock is clock and isinstance(c.commands, CommandRouter)


def test_router_included(stub_n, settings, clock, tmp_path):
    app = make(settings, clock, {"nasa"})
    with TestClient(app) as c:
        assert c.get("/api/nasa/ping").json() == {"pong": True}
    assert CALLS["DonkiCache"][0][0] == (tmp_path / "nasa",)
    args = CALLS["NasaState"][0][0]
    assert args[2] is clock and args[3] == ("crew-a", "crew-b", "crew-c")
    app = make(settings, clock, {"serial"})
    assert not hasattr(app.state, "nasa")
    assert TestClient(app).get("/api/nasa/ping").status_code == 404


def test_missing_module_starts(monkeypatch, settings, clock, caplog):
    monkeypatch.setitem(sys.modules, "hub.wearable.routes", None)
    monkeypatch.setitem(sys.modules, "hub.wearable", None)
    with caplog.at_level(logging.WARNING):
        app = make(settings, clock, {"wearable"})
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
    assert "wearable" in app.state.features.skipped and "wearable" in caplog.text


def test_nasa_parts_optional(monkeypatch, tmp_path, settings, clock):
    mods, _, _ = build_stubs(tmp_path, actuator=False, dose=False)
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    monkeypatch.setitem(sys.modules, "hub.nasa.actuator", None)
    monkeypatch.setitem(sys.modules, "hub.nasa.dose", None)
    app = make(settings, clock, {"nasa"})
    with TestClient(app) as c:
        assert c.get("/api/nasa/ping").status_code == 200
    st = app.state.nasa
    assert st.policy is None and st.dose is None
    assert {"nasa.actuator", "nasa.dose"} <= set(app.state.features.skipped)
    assert CALLS["run_poller"][0][1]["after_poll"] == []


def test_mount_order_and_camera(stub_n, settings, clock, tmp_path):
    cam, con = tmp_path / "cam", tmp_path / "con"
    for d, t in ((cam, "habitat-camera-test"), (con, "habitat-console-test")):
        d.mkdir()
        (d / "index.html").write_text(t)
    app = make(settings, clock, {"mcp"}, camera_dist=cam, console_dist=con)
    with TestClient(app) as c:
        assert c.get("/mcp/").text == "mcp-stub"
        assert "habitat-camera-test" in c.get("/camera/").text
        assert "habitat-console-test" in c.get("/").text
        assert c.get("/api/status").json()["results"] == []
    assert len(CALLS["build_mcp"]) == 1


def test_camera_missing_503(settings, clock, tmp_path):
    con = tmp_path / "con"
    con.mkdir()
    (con / "index.html").write_text("habitat-console-test")
    with TestClient(make(settings, clock, set(), console_dist=con)) as c:
        r = c.get("/camera/")
        assert r.status_code == 503 and "npm --prefix camera run build" in r.text
        assert "habitat-console-test" in c.get("/").text


def test_lifespan_hooks(stub_n, settings, clock):
    app = make(settings, clock, {"nasa", "iss", "wearable", "mcp"})
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
        assert len(CALLS["run_poller"]) == 1 and CALLS["iss_start"] and CALLS["mcp_enter"]
    pol = CALLS["ActuatorPolicy"][0]
    assert pol[0][0] is app.state.ctx.commands and pol[0][1] is app.state.ingestor
    assert pol[1]["crews"] == ("crew-a", "crew-b", "crew-c")
    after = CALLS["run_poller"][0][1]["after_poll"]
    assert len(after) == 2
    assert CALLS["IssLiveClient"][0][0][0] == ["ITEM_A", "ITEM_B"]
    assert CALLS["iss_stop"] and CALLS["mcp_exit"] and stub_n.stopped
    w = CALLS["WearableState"][0][0]
    assert w[1] == ("crew-a", "crew-b", "crew-c") and str(w[2]()) == "2026-11-14"


def test_iss_start_failure_survives(stub_n, settings, clock, caplog):
    def boom(self):
        raise RuntimeError("no network")

    stub_n.mods["hub.nasa.isslive_client"].IssLiveClient.start = boom
    app = make(settings, clock, {"nasa", "iss"})
    with caplog.at_level(logging.ERROR), TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
    assert "iss" in caplog.text and CALLS["run_poller"]


def test_iss_needs_nasa(stub_n, settings, clock):
    app = make(settings, clock, {"iss"})
    assert app.state.features.skipped["iss"] == "needs nasa"
    assert "IssLiveClient" not in CALLS


def badge(app, node, payload, topic_node=None):
    from hub.mqtt import route_message

    topic = f"habitat/v1/badge/{topic_node or node}"
    route_message(app.state.ingestor, app.state.nodes, topic, json.dumps(payload).encode(),
                  app.state.mqtt_handlers)  # fmt: skip


def test_badge_routing(stub_n, settings, clock):
    app = make(settings, clock, {"nasa"})
    b = {"v": 1, "node": "cabin-1", "boot": 3, "seq": 9, "crew": "crew-b"}
    badge(app, "cabin-1", b)
    assert app.state.crew.get("cabin-1") == "crew-b"
    assert len(CALLS["on_badge"]) == 1 and CALLS["on_badge"][0][0][:2] == ("cabin-1", "crew-b")
    badge(app, "cabin-1", {**b, "type": "badge", "age_ms": 0, "seq": 10})
    assert len(CALLS["on_badge"]) == 2
    badge(app, "cabin-1", {**b, "crew": "unknown"})
    badge(app, "cabin-1", {**b, "node": "vitals-1"}, topic_node="cabin-1")
    assert len(CALLS["on_badge"]) == 2
    app2 = make(settings, clock, {"serial"})
    badge(app2, "cabin-1", b)
    assert app2.state.crew.get("cabin-1") == "crew-b"


def test_food_wiring(stub_n, settings, clock):
    app = make(settings, clock, {"food"})
    with TestClient(app) as c:
        assert c.get("/api/food/ping").status_code == 200
        assert c.get("/api/food/ctx-check").json() == {
            "store": True, "assessor": True, "tz": "America/Sao_Paulo",
        }  # fmt: skip
    assert CALLS["load_catalog"][0][0] == (settings.food_catalog_path,)
    a, k = CALLS["FoodWriter"][0]
    assert a[0] is app.state.store and a[1] is app.state.ingestor and a[3] is clock
    assert k["boot"] == int(clock().timestamp()) == 1794657600
    assert app.state.food_catalog and app.state.food_writer
    app2 = make(settings, clock, {"serial"})
    assert TestClient(app2).get("/api/food/ping").status_code == 404
    assert not hasattr(app2.state, "food_writer") and app2.state.ctx


def test_food_broken_catalog(stub_n, settings, clock, caplog):
    def bad(path):
        raise stub_n.CatalogError("bad item fx-bar")

    stub_n.mods["hub.food.catalog"].load_catalog = bad
    with caplog.at_level(logging.ERROR):
        app = make(settings, clock, {"food"})
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/food/ping").status_code == 404
    assert "fx-bar" in app.state.features.skipped["food"] and "food" in caplog.text


def test_food_module_missing(monkeypatch, settings, clock, caplog):
    monkeypatch.setitem(sys.modules, "hub.food.routes", None)
    with caplog.at_level(logging.WARNING):
        app = make(settings, clock, {"food"})
    assert "food" in app.state.features.skipped and "food" in caplog.text


def test_food_rules_load_without_feature(settings, clock):
    app = make(settings, clock, {"serial"}, thresholds_path=MAIN_RULES,
               food_thresholds_path=FOOD_RULES)  # fmt: skip
    m = {"v": 1, "node": "food", "boot": 1, "seq": 1, "age_ms": 0, "ind": "intake_sodium_mg",
         "val": 2400, "unit": "mg", "src": "self", "dev": "catalog", "q": ["ok"],
         "crew": "crew-a"}  # fmt: skip
    with TestClient(app) as c:
        e = c.post("/api/readings", json=m).json()["results"][0]
    assert e["rule_id"] == "t_na_max" and e["status"] == "watch"
