import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.contract import ContractError
from hub.crew import Badge, CrewRegistry, parse_badge
from hub.store import Store
from hub.tests.helpers import msg

B = {"v": 1, "node": "cabin-1", "boot": 3, "seq": 9, "crew": "crew-b"}


def reason(raw, **kw):
    with pytest.raises(ContractError) as e:
        parse_badge(raw, **kw)
    return e.value.reason


def test_parse_badge():
    assert parse_badge(B) == Badge(1, "cabin-1", 3, 9, "crew-b")
    assert parse_badge({**B, "type": "badge", "age_ms": 0}) == parse_badge(B)
    assert reason({**B, "crew": "unknown"}) == "bad_crew"
    assert reason({k: v for k, v in B.items() if k != "crew"}) == "missing_field:crew"
    assert reason({**B, "v": 2}) == "bad_version"
    assert reason({**B, "node": "vitals-1"}, expected_node="cabin-1") == "topic_node_mismatch"


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        c.n = 0
        yield c


def hr(c, **kw):
    c.n += 1
    body = msg(node="vitals-1", seq=c.n, ind="hr", unit="bpm", val=70, dev="MAX30102", **kw)
    r = c.post("/api/readings", json=body)
    assert r.status_code == 201
    return c.get("/api/readings?ind=hr").json()[-1]["crew"]


def test_post_crew(client):
    r = client.post("/api/crew", json={"node": "vitals-1", "crew": "crew-a"})
    assert r.status_code == 200 and r.json() == {"node": "vitals-1", "crew": "crew-a"}
    assert hr(client) == "crew-a"
    client.n += 1
    t = msg(seq=client.n, ind="cabin_temp", unit="C", val=22, dev="BME280")
    client.post("/api/readings", json=t)
    assert client.get("/api/readings?ind=cabin_temp").json()[0]["crew"] is None
    client.post("/api/crew", json={"node": "vitals-1", "crew": None})
    assert hr(client) is None


def test_post_crew_validation(client):
    assert client.post("/api/crew", json={"node": "vitals-9", "crew": "crew-a"}).json() == {
        "reason": "unknown_node"
    }
    assert client.post("/api/crew", json={"node": "vitals-1", "crew": "crew-z"}).json() == {
        "reason": "bad_crew"
    }
    assert client.post("/api/crew", json={"crew": "crew-a"}).json() == {
        "reason": "missing_field:node"
    }


def test_badge_sets_crew(client, tmp_path):
    reg: CrewRegistry = client.app.state.crew
    reg.on_badge(Badge(1, "cabin-1", 1, 1, "crew-c"))
    assert reg.get("cabin-1") == "crew-c"
    m = msg(ind="skin_temp", unit="C", val=33.0, dev="MLX90614")
    client.post("/api/readings", json=m)
    assert client.get("/api/readings?ind=skin_temp").json()[0]["crew"] == "crew-c"


def test_crew_applies_to_intake(client):
    client.post("/api/crew", json={"node": "manual", "crew": "crew-b"})
    base = {"node": "manual", "src": "self", "dev": "manual"}
    k = msg(seq=1, ind="intake_kcal", unit="kcal", val=500, **base)
    b = msg(seq=2, ind="body_mass", unit="kg", val=70, **base)
    t = msg(seq=3, ind="cabin_temp", unit="C", val=22, node="manual", dev="manual")
    for m in (k, b, t):
        assert client.post("/api/readings", json=m).status_code == 201
    got = {i: client.get(f"/api/readings?ind={i}").json()[0]["crew"]
           for i in ("intake_kcal", "body_mass", "cabin_temp")}  # fmt: skip
    assert got == {"intake_kcal": "crew-b", "body_mass": "crew-b", "cabin_temp": None}


def test_explicit_crew_wins(client):
    client.post("/api/crew", json={"node": "vitals-1", "crew": "crew-a"})
    assert hr(client, crew="crew-b") == "crew-b"


def test_persisted(tmp_path, clock):
    s = Store(tmp_path / "c.db")
    CrewRegistry(s, clock).set("vitals-1", "crew-a")
    s.close()
    s2 = Store(tmp_path / "c.db")
    reg = CrewRegistry(s2, clock)
    assert reg.get("vitals-1") == "crew-a" and reg.snapshot() == {"vitals-1": "crew-a"}
