import logging
import sys
from dataclasses import replace

from fastapi.testclient import TestClient

from hub.api import create_app


def app_with(settings, clock, features=frozenset({"signals"})):
    return create_app(replace(settings, features=features), clock=clock)


def test_signals_lists_cabin_once_and_body_per_crew(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals").json()
    ids = [(s["id"], s["crew"]) for s in body["signals"]]
    assert ("cabin_temp_6h", None) in ids
    assert {crew for i, crew in ids if i == "rest_hr_baseline"} == set(settings.crews)
    assert all(s["state"] == "not_enough_data" for s in body["signals"])  # an empty hub


def test_signals_crew_filter_and_at(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals", params={"crew": "crew-a", "at": "2026-11-14T09:00:00Z"}).json()
    assert body["crew"] == "crew-a" and body["at"] == "2026-11-14T09:00:00.000Z"
    assert {s["crew"] for s in body["signals"]} == {None, "crew-a"}


def test_signals_rejects_bad_crew_bad_at_unknown_id(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        assert c.get("/api/signals", params={"crew": "crew-z"}).json() == {"reason": "bad_crew"}
        assert c.get("/api/signals", params={"at": "2026-11-14T09:00:00"}).status_code == 422
        assert c.get("/api/signals/nope").status_code == 404


def test_one_signal(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals/cabin_rh_ttl").json()
    [s] = body["signals"]
    assert s["id"] == "cabin_rh_ttl" and s["kind"] == "time_to_limit" and s["can_trigger"]


def test_signals_feature_off_is_404(settings, clock):
    with TestClient(app_with(settings, clock, frozenset({"serial"}))) as c:
        assert c.get("/api/signals").status_code == 404


def test_broken_signals_module_leaves_hub_starting(monkeypatch, settings, clock, caplog):
    monkeypatch.setitem(sys.modules, "hub.signals.routes", None)
    with caplog.at_level(logging.WARNING):
        app = app_with(settings, clock)
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
    assert "signals" in app.state.features.skipped and "signals" in caplog.text
