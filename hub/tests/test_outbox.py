from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import FOOD_RULES, MAIN_RULES, msg

REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


@pytest.fixture
def client(settings, clock):
    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    with TestClient(create_app(s, clock=clock)) as c:
        yield c


def temp(seq, val):
    return msg(seq=seq, ind="cabin_temp", unit="C", val=val, dev="BME280")


def seeded(c):
    c.post("/api/readings", json=temp(1, 22.0))
    c.post("/api/readings", json=temp(2, 26.0))
    c.post("/api/reps", json=REP)
    return c.get("/api/outbox?after=0").json()


def test_outbox_sequence(client):
    b = seeded(client)
    ids = [i["id"] for i in b["items"]]
    assert ids == sorted(set(ids))
    assert [i["kind"] for i in b["items"]] == ["reading", "reading", "alert", "rep"]
    assert b["last_id"] == ids[-1]


def test_reading_payload_status(client):
    p = seeded(client)["items"][1]["payload"]
    assert (p["ind"], p["val"], p["status"], p["rule_id"], p["source_kind"], p["escalate_to"]) == (
        "cabin_temp", 26.0, "watch", "cabin_performance_temp", "nasa_std", "cmo",
    )  # fmt: skip
    assert p["id"] and p["measured_at"]


def test_after_cursor(client):
    b = seeded(client)
    second = b["items"][1]["id"]
    got = client.get(f"/api/outbox?after={second}").json()
    assert [i["kind"] for i in got["items"]] == ["alert", "rep"]


def test_empty_tail(client):
    b = seeded(client)
    got = client.get(f"/api/outbox?after={b['last_id']}").json()
    assert got == {"items": [], "last_id": b["last_id"]}


def test_limit(client):
    store = client.app.state.store
    from datetime import UTC, datetime

    for i in range(1200):
        store.append_outbox("reading", {"i": i}, datetime(2026, 11, 14, tzinfo=UTC))
    n = lambda q: len(client.get(f"/api/outbox?after=0{q}").json()["items"])
    assert (n(""), n("&limit=1000"), n("&limit=5000")) == (500, 1000, 1000)


def test_validation(client):
    assert client.get("/api/outbox?after=-1").json() == {"reason": "bad_value:after"}
    assert client.get("/api/outbox?after=abc").json() == {"reason": "bad_type:after"}
    assert client.get("/api/outbox").status_code == 200


def test_excludes_load_raw_and_duplicates(client):
    for i in range(80):
        raw = msg(
            node="exercise-1", boot=1, seq=i + 1, ind="load_raw", unit="N", val=1, dev="HX711"
        )
        client.post("/api/readings", json=raw)
    client.post("/api/readings", json=temp(1, 22.0))
    client.post("/api/readings", json=temp(1, 22.0))
    items = client.get("/api/outbox").json()["items"]
    assert len(items) == 1 and items[0]["payload"]["ind"] == "cabin_temp"


def test_derived_included(client):
    client.post("/api/readings", json=msg(seq=1, ind="cabin_p", unit="hPa", val=1000, dev="BME280"))
    client.post("/api/readings", json=msg(seq=2))
    inds = {i["payload"]["ind"]: i["payload"] for i in client.get("/api/outbox").json()["items"]}
    assert inds["cabin_ppco2"]["derived_from"] is not None


def test_intake_included(client):
    m = {"v": 1, "node": "food", "boot": 1, "seq": 1, "age_ms": 0, "ind": "intake_sodium_mg",
         "val": 210, "unit": "mg", "src": "self", "dev": "catalog", "q": ["ok"]}  # fmt: skip
    client.post("/api/readings", json=m)
    (item,) = client.get("/api/outbox").json()["items"]
    p = item["payload"]
    assert (p["ind"], p["node"], p["src"], p["dev"]) == (
        "intake_sodium_mg",
        "food",
        "self",
        "catalog",
    )
    assert {"status", "rule_id", "source_kind", "escalate_to"} <= set(p)
