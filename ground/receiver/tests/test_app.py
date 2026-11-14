import pytest
from fastapi.testclient import TestClient

from receiver.app import create_app

T = "2026-11-15T13:00:12.000Z"
BEACON = {
    "link": {
        "state": "contact",
        "light_time_s": 720,
        "time_scale": 60,
        "queue_len": 0,
        "last_blackout": None,
    },
    "hold_s": 12.0,
    "in_flight": 0,
    "fetched_id": 3,
    "delivered_id": 0,
    "last_blackout_cause": None,
    "sent_at": T,
}


def _item(i: int) -> dict:
    return {"id": i, "kind": "reading", "created_at": T, "payload": {"n": i}}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "g.db", None))


def _post(client, ids, beacon=BEACON):
    return client.post("/ground/ingest", json={"beacon": beacon, "items": [_item(i) for i in ids]})


def test_ingest_stores(client):
    r = _post(client, [1, 2, 3])
    assert r.status_code == 200 and r.json() == {"max_id": 3, "stored": 3}


def test_ingest_idempotent(client):
    _post(client, [1, 2, 3])
    assert _post(client, [1, 2, 3]).json() == {"max_id": 3, "stored": 0}
    s = client.get("/ground/summary").json()
    assert s["stored"] == 3 and s["min_id"] == 1 and s["max_id"] == 3
    assert s["missing_ids"] == 0 and s["arrivals"] == 2
    assert s["last_arrival_at"].endswith("Z")


def test_missing_ids(client):
    _post(client, [1, 2, 4])
    assert client.get("/ground/summary").json()["missing_ids"] == 1


def test_arrivals_order_and_dedupe(client):
    _post(client, [1, 2])
    _post(client, [2, 3])
    a = client.get("/ground/arrivals?after=0").json()
    assert [x["arrival_id"] for x in a] == [1, 2]
    assert [i["id"] for i in a[1]["items"]] == [3]
    assert [x["arrival_id"] for x in client.get("/ground/arrivals?after=1").json()] == [2]


def test_arrivals_limit(client):
    for i in range(1, 6):
        _post(client, [i])
    a = client.get("/ground/arrivals?after=0&limit=2").json()
    assert [x["arrival_id"] for x in a] == [1, 2]
    assert client.get("/ground/arrivals?after=0&limit=5000").status_code == 422


def test_beacon_only_fresh(client):
    r = client.post("/ground/ingest", json={"beacon": BEACON, "items": []})
    assert r.json() == {"max_id": None, "stored": 0}
    a = client.get("/ground/arrivals?after=0").json()
    assert len(a) == 1 and a[0]["items"] == [] and a[0]["beacon"] == BEACON


def test_beacon_only_after_items(client):
    _post(client, [1, 2, 3])
    r = client.post("/ground/ingest", json={"beacon": BEACON, "items": []})
    assert r.json() == {"max_id": 3, "stored": 0}


def test_rejects_item_without_id(client):
    bad = {"kind": "reading", "created_at": T, "payload": {}}
    r = client.post("/ground/ingest", json={"beacon": None, "items": [bad]})
    assert r.status_code == 422
    assert client.get("/ground/summary").json()["stored"] == 0


def test_static_index(tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>x</title>")
    c = TestClient(create_app(tmp_path / "g.db", static))
    r = c.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_no_static_is_404(client):
    assert client.get("/").status_code == 404
