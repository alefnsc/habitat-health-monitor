import logging
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import msg


def test_serves_console(settings, clock, tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>habitat-console-test</html>")
    (d / "assets" / "app.js").write_text("console.log(1)")
    with TestClient(create_app(replace(settings, console_dist=d), clock=clock)) as c:
        assert "habitat-console-test" in c.get("/").text
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/api/status").json()["results"] == []


def test_console_missing(settings, clock, tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    with TestClient(create_app(replace(settings, console_dist=d), clock=clock)) as c:
        r = c.get("/")
        assert r.status_code == 503 and "npm --prefix console run build" in r.text
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/nope").status_code == 404


def test_no_thresholds_still_starts(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        assert c.get("/api/status").status_code == 200
        body = msg(ind="cabin_temp", unit="C", val=22.0, dev="BME280")
        assert c.post("/api/readings", json=body).json()["results"][0]["status"] == "unknown"


def test_clock_sanity_warning(settings, caplog):
    with caplog.at_level(logging.WARNING):
        create_app(settings, clock=lambda: datetime(2000, 1, 1, tzinfo=UTC))
    assert "hub clock" in caplog.text
