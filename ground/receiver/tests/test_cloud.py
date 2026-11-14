import json

from fastapi.testclient import TestClient

from receiver.app import create_app
from receiver.cloud import CACHE, create_cloud_app
from receiver.kv import MemoryKV
from receiver.redis_store import RedisStore
from receiver.signing import HEADER, sign

T = "2026-11-14T15:00:00.000Z"
BATCH = {
    "beacon": {"state": "contact"},
    "items": [
        {"id": 1, "kind": "reading", "created_at": T, "payload": {"ind": "cabin_co2", "val": 900}},
        {"id": 2, "kind": "reading", "created_at": T, "payload": {"ind": "hr", "crew": "crew-a"}},
    ],
}


def cloud(secret="k"):
    return TestClient(create_cloud_app(RedisStore(MemoryKV()), secret))


def post(c, body: dict, secret="k", path="/ground/ingest"):
    raw = json.dumps(body).encode()
    return c.post(path, content=raw, headers={HEADER: sign(raw, secret), "content-type": "application/json"})


def test_signed_ingest_and_reads():
    c = cloud()
    r = post(c, BATCH)
    assert r.status_code == 200 and r.json() == {"max_id": 2, "stored": 2}
    arr = c.get("/ground/arrivals?after=0")
    assert arr.status_code == 200 and arr.headers["cache-control"] == CACHE
    assert [x["id"] for x in arr.json()[0]["items"]] == [1, 2]
    sm = c.get("/ground/summary").json()
    assert sm["stored"] == 2 and sm["last_arrival_at"]


def test_api_prefix_also_served():
    c = cloud()
    assert post(c, BATCH, path="/api/ground/ingest").status_code == 200
    assert c.get("/api/ground/summary").json()["stored"] == 2


def test_bad_or_missing_signature_401():
    c = cloud()
    raw = json.dumps(BATCH).encode()
    assert c.post("/ground/ingest", content=raw).status_code == 401
    assert post(c, BATCH, secret="wrong").status_code == 401
    assert c.get("/ground/summary").json()["stored"] == 0


def test_empty_secret_refuses_writes():
    c = cloud(secret="")
    assert post(c, BATCH, secret="").status_code == 401


def test_bad_body_422_and_limits_413():
    c = cloud()
    assert post(c, {"items": [{"id": "x"}]}).status_code == 422
    many = {"beacon": None, "items": [
        {"id": i, "kind": "reading", "created_at": T, "payload": {}} for i in range(1, 1002)
    ]}
    assert post(c, many).status_code == 413
    big = TestClient(create_cloud_app(RedisStore(MemoryKV()), "k", max_body=100))
    assert post(big, BATCH).status_code == 413


def test_signed_purge():
    c = cloud()
    post(c, BATCH)
    raw = json.dumps({"crew": "crew-a"}).encode()
    assert c.post("/ground/purge", content=raw).status_code == 401
    r = c.post("/ground/purge", content=raw, headers={HEADER: sign(raw, "k")})
    assert r.status_code == 200 and r.json() == {"removed": 1}
    assert c.get("/ground/summary").json()["stored"] == 1


def test_same_shapes_as_local_receiver(tmp_path):
    local = TestClient(create_app(tmp_path / "g.db", None))
    c = cloud()
    local.post("/ground/ingest", json=BATCH)
    post(c, BATCH)
    la, ca = local.get("/ground/arrivals?after=0").json(), c.get("/ground/arrivals?after=0").json()
    assert la[0].keys() == ca[0].keys()
    assert la[0]["items"] == ca[0]["items"] and la[0]["beacon"] == ca[0]["beacon"]
    ls, cs = local.get("/ground/summary").json(), c.get("/ground/summary").json()
    assert ls.keys() == cs.keys()
    for k in ("stored", "min_id", "max_id", "missing_ids", "arrivals"):
        assert ls[k] == cs[k]
