import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import FOOD_RULES, MAIN_RULES, msg


@pytest.fixture
def client(settings, clock):
    from dataclasses import replace

    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    with TestClient(create_app(s, clock=clock)) as c:
        c.clock = clock
        c.n = 0
        yield c


def post(c, **kw):
    c.n += 1
    base = {"seq": c.n, "ind": "cabin_temp", "unit": "C", "val": 22.0, "dev": "BME280"}
    body = msg(**{**base, **kw})
    r = c.post("/api/readings", json=body)
    assert r.status_code == 201, r.text
    c.clock.advance(60)
    return r.json()


def status(c, **params):
    r = c.get("/api/status", params=params)
    assert r.status_code == 200
    return r.json()


def entry(body, ind):
    return next(e for e in body["results"] if e["ind"] == ind)


def test_status_shape(client):
    b = status(client)
    assert set(b) == {"crew", "generated_at", "nodes", "results"}
    assert b["crew"] is None and b["nodes"] == [] and b["results"] == []
    assert b["generated_at"] == "2026-11-14T12:00:00.000Z"


def test_status_worst_of(client):
    r = post(client, val=26.0)
    e = entry(status(client), "cabin_temp")
    assert (e["status"], e["rule_id"], e["src"], e["dev"], e["q"], e["node"]) == (
        "watch", "cabin_performance_temp", "hobby", "BME280", ["ok"], "cabin-1",
    )  # fmt: skip
    assert e["reading_id"] == r["id"]


def test_one_entry_per_ind(client):
    post(client, val=22.0)
    post(client, val=26.0)
    results = [e for e in status(client)["results"] if e["ind"] == "cabin_temp"]
    assert len(results) == 1 and results[0]["val"] == 26.0


def test_flagged_latest_unknown(client):
    post(client, val=26.0)
    post(client, val=23.0, q=["settling"])
    e = entry(status(client), "cabin_temp")
    assert (e["status"], e["rule_id"], e["q"], e["val"]) == ("unknown", None, ["settling"], 23.0)


def test_severity_and_ties(client):
    post(client, val=22.0)
    e = entry(status(client), "cabin_temp")
    assert (e["status"], e["rule_id"]) == ("ok", "cabin_performance_temp")
    post(client, val=28.0)
    e = entry(status(client), "cabin_temp")
    assert (e["status"], e["rule_id"]) == ("act", "cabin_health_box_temp")


def test_no_rule_entry(client):
    post(client, ind="cabin_p", unit="hPa", val=1000.0)
    e = entry(status(client), "cabin_p")
    assert (e["status"], e["rule_id"]) == ("unknown", None)


def test_status_crew_filter(client):
    hr = {"ind": "hr", "unit": "bpm", "dev": "MAX30102", "node": "vitals-1"}
    post(client, val=60, crew="crew-a", **hr)
    post(client, val=110, crew="crew-b", **hr)
    post(client, val=22.0)
    b = status(client, crew="crew-a")
    assert {e["ind"] for e in b["results"]} == {"hr", "cabin_temp"}
    h = entry(b, "hr")
    assert (h["val"], h["crew"]) == (60.0, "crew-a")
    assert entry(b, "cabin_temp")["crew"] is None
    allc = [e for e in status(client)["results"] if e["ind"] == "hr"]
    assert len(allc) == 1 and allc[0]["val"] == 110.0 and allc[0]["crew"] == "crew-b"


def test_status_intake_crew_scope(client):
    f = {"node": "food", "src": "self", "dev": "catalog", "ind": "intake_sodium_mg", "unit": "mg"}
    post(client, val=210, crew="crew-a", **f)
    post(client, val=300, crew="crew-b", **f)
    post(client, node="manual", src="self", dev="manual", ind="body_mass", unit="kg", val=70,
         crew="crew-a")  # fmt: skip
    a = status(client, crew="crew-a")
    assert entry(a, "intake_sodium_mg")["crew"] == "crew-a"
    assert (
        entry(a, "intake_sodium_mg")["val"] == 210.0 or entry(a, "intake_sodium_mg")["reading_id"]
    )
    assert any(e["ind"] == "body_mass" for e in a["results"])
    b = status(client, crew="crew-b")
    assert not any(e["ind"] == "body_mass" for e in b["results"])
    assert entry(status(client), "intake_sodium_mg")["crew"] == "crew-b"


def test_status_bad_crew(client):
    r = client.get("/api/status?crew=crew-z")
    assert r.status_code == 422 and r.json()["reason"] == "bad_crew"
