import pytest
from fastapi.testclient import TestClient

from hub.api import app_factory, create_app

GLU = {
    "v": 1, "node": "manual", "boot": 1763121600, "seq": 1, "age_ms": 0, "ind": "glucose",
    "val": 95, "unit": "mg/dL", "src": "certified", "dev": "manual", "q": ["ok"],
    "crew": "crew-a",
}  # fmt: skip
REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        yield c


def test_post_manual_glucose(client):
    r = client.post("/api/readings", json=GLU)
    assert r.status_code == 201
    b = r.json()
    assert isinstance(b["id"], int) and b["duplicate"] is False
    assert b["measured_at"] == "2026-11-14T12:00:00.000Z"
    (e,) = b["results"]
    assert (e["ind"], e["node"], e["src"], e["reading_id"]) == (
        "glucose",
        "manual",
        "certified",
        b["id"],
    )


def test_post_duplicate(client):
    a = client.post("/api/readings", json=GLU).json()
    r = client.post("/api/readings", json=GLU)
    assert r.status_code == 200
    b = r.json()
    assert b["duplicate"] is True and b["id"] == a["id"] and b["results"] == []


def test_post_contract_error(client):
    r = client.post("/api/readings", json={**GLU, "unit": "mmol/L"})
    assert r.status_code == 422 and r.json() == {"reason": "unit_mismatch"}
    r = client.post("/api/readings", content=b"hello")
    assert r.status_code == 422 and r.json()["reason"] == "bad_json"


def test_post_no_size_limit_on_http(client):
    r = client.post("/api/readings", json={**GLU, "pad": "x" * 400})
    assert r.status_code == 201


def test_post_intake(client):
    m = {
        "v": 1, "node": "food", "boot": 1763121600, "seq": 1, "age_ms": 0,
        "ind": "intake_sodium_mg", "val": 210, "unit": "mg", "src": "self", "dev": "catalog",
        "q": ["ok"], "crew": "crew-a",
    }  # fmt: skip
    r = client.post("/api/readings", json=m)
    assert r.status_code == 201 and r.json()["results"][0]["ind"] == "intake_sodium_mg"
    r = client.post("/api/readings", json={**m, "seq": 2, "unit": "g"})
    assert r.status_code == 422 and r.json()["reason"] == "unit_mismatch"


def post_three(client, clock):
    for i, v in enumerate((90, 95, 100)):
        client.post("/api/readings", json={**GLU, "seq": i + 1, "val": v})
        clock.advance(60)


def test_get_history(client, clock):
    post_three(client, clock)
    rows = client.get("/api/readings?ind=glucose&limit=2").json()
    assert [r["val"] for r in rows] == [95, 100]
    for k in ("id", "measured_at", "received_at", "src", "dev", "q", "crew", "derived_from"):
        assert k in rows[0]
    assert rows[0]["derived_from"] is None and rows[0]["clash"] == 0


def test_get_since_and_crew(client, clock):
    post_three(client, clock)
    url = "/api/readings?ind=glucose&since=2026-11-14T12:01:00.000Z&crew=crew-a"
    assert [r["val"] for r in client.get(url).json()] == [95, 100]


def test_get_validation(client):
    assert (
        client.get("/api/readings?ind=glucose&since=yesterday").json()["reason"]
        == "bad_value:since"
    )
    assert client.get("/api/readings?ind=heart").json()["reason"] == "unknown_ind"
    assert client.get("/api/readings?ind=glucose&limit=99999").status_code == 200
    r = client.get("/api/readings")
    assert r.status_code == 422 and r.json()["reason"] == "missing_field:ind"


def test_post_rep(client):
    assert client.post("/api/reps", json=REP).status_code == 201
    r = client.post("/api/reps", json=REP)
    assert r.status_code == 200 and r.json()["duplicate"] is True
    r = client.post("/api/reps", json={**REP, "seq": 2, "t1_ms": 100})
    assert r.status_code == 422 and r.json()["reason"] == "bad_value:t1_ms"


def test_cors(client):
    r = client.options(
        "/api/readings",
        headers={"Origin": "http://192.168.4.20:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["access-control-allow-origin"] == "*"


def test_derived_in_history_and_response(client, clock):
    base = {"v": 1, "node": "cabin-1", "boot": 2, "age_ms": 0, "src": "hobby", "dev": "BME280",
            "q": ["ok"]}  # fmt: skip
    client.post(
        "/api/readings", json={**base, "seq": 1, "ind": "cabin_p", "val": 1000.0, "unit": "hPa"}
    )
    clock.advance(30)
    r = client.post("/api/readings", json={**base, "seq": 2, "dev": "SCD41", "ind": "cabin_co2",
                                           "val": 4000, "unit": "ppm"})  # fmt: skip
    assert [e["ind"] for e in r.json()["results"]] == ["cabin_co2", "cabin_ppco2"]
    rows = client.get("/api/readings?ind=cabin_ppco2").json()
    assert len(rows) == 1 and rows[0]["val"] == pytest.approx(3.000248, abs=1e-6)


def test_app_factory(monkeypatch, tmp_path):
    monkeypatch.setenv("HUB_DB", str(tmp_path / "f.db"))
    with TestClient(app_factory()) as c:
        r = c.get("/api/readings?ind=hr")
        assert r.status_code == 200 and r.json() == []
