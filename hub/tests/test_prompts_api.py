from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import FOOD_RULES, MAIN_RULES


@pytest.fixture
def client(settings, clock):
    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    with TestClient(create_app(s, clock=clock)) as c:
        c.frames = []
        c.n = 0
        orig = c.app.state.prompts.emit
        c.app.state.prompts.emit = lambda t, d: (c.frames.append((t, d)), orig(t, d))
        yield c


def r(c, ind, val, unit, **kw):
    c.n += 1
    return {
        "v": 1, "node": "manual", "boot": 1763121600, "seq": c.n, "age_ms": 0, "ind": ind,
        "val": val, "unit": unit, "src": "self", "dev": "manual", "q": ["ok"], "crew": "crew-a",
        **kw,
    }  # fmt: skip


def morning(c, crew="crew-a"):
    return c.post("/api/prompts", json={"kind": "morning", "crew": crew}).json()["id"]


def test_answer(client):
    pid = morning(client)
    body = {"readings": [r(client, "body_temp", 36.8, "C"), r(client, "hr", 64, "bpm"),
                         r(client, "sleep_h", 7.5, "h"), r(client, "mood", 4, "1-5")]}  # fmt: skip
    res = client.post(f"/api/prompts/{pid}/answer", json=body)
    assert res.status_code == 200
    b = res.json()
    assert b["prompt_id"] == pid and len(b["reading_ids"]) == 4 and len(b["results"]) == 4
    assert client.get("/api/prompts").json() == []
    assert [p["status"] for p in client.get("/api/prompts?status=all").json()] == ["answered"]
    assert client.app.state.prompts.answer_links(pid) == sorted(b["reading_ids"])
    (item,) = [i for i in client.get("/api/outbox").json()["items"] if i["kind"] == "prompt_answer"]
    p = item["payload"]
    assert (p["prompt_kind"], p["crew"], p["status"], p["reading_ids"], p["trigger_reading_id"]) == (
        "morning", "crew-a", "answered", b["reading_ids"], None,
    )  # fmt: skip
    assert p["answered_at"] == "2026-11-14T12:00:00.000Z"
    assert ("prompt", client.get("/api/prompts?status=all").json()[0]) in client.frames


def test_answer_symptom_code(client):
    client.post("/api/readings", json={
        "v": 1, "node": "cabin-1", "boot": 2, "seq": 1, "age_ms": 0, "ind": "cabin_temp",
        "val": 26.0, "unit": "C", "src": "hobby", "dev": "BME280", "q": ["ok"]})  # fmt: skip
    (p,) = client.get("/api/prompts").json()
    sym = r(client, "symptom", 1, "code", code="headache", crew="crew-b")
    res = client.post(f"/api/prompts/{p['id']}/answer", json={"readings": [sym]})
    assert res.status_code == 200
    row = client.get("/api/readings?ind=symptom").json()[0]
    assert row["code"] == "headache"
    items = [i for i in client.get("/api/outbox").json()["items"] if i["kind"] == "prompt_answer"]
    assert items[0]["payload"]["trigger_reading_id"] == p["trigger_reading_id"]


def test_skip(client):
    pid = morning(client)
    res = client.post(f"/api/prompts/{pid}/answer", json={"readings": [], "skipped": True})
    assert (
        res.status_code == 200 and res.json()["reading_ids"] == [] and res.json()["results"] == []
    )
    assert client.get("/api/prompts?status=all").json()[0]["status"] == "skipped"
    items = client.get("/api/outbox").json()["items"]
    item = next(i for i in items if i["kind"] == "prompt_answer")
    assert item["payload"]["status"] == "skipped"


def test_answer_errors(client):
    pid = morning(client)
    url = f"/api/prompts/{pid}/answer"
    assert client.post("/api/prompts/999/answer", json={"readings": []}).status_code == 404
    g = r(client, "glucose", 95, "mg/dL")
    assert client.post(url, json={"readings": [g]}).json() == {"reason": "ind_not_asked"}
    other = r(client, "mood", 3, "1-5", crew="crew-b")
    assert client.post(url, json={"readings": [other]}).json() == {"reason": "crew_mismatch"}
    four = [r(client, "body_temp", 36.8, "F"), r(client, "hr", 64, "bpm"),
            r(client, "sleep_h", 7, "h"), r(client, "mood", 4, "1-5")]  # fmt: skip
    n = client.get("/api/readings?ind=hr").json()
    assert client.post(url, json={"readings": four}).json() == {"reason": "unit_mismatch"}
    assert client.get("/api/readings?ind=hr").json() == n
    assert client.get("/api/readings?ind=mood").json() == []
    assert client.post(url, json={"readings": []}).json() == {"reason": "bad_value:readings"}
    both = {"readings": [r(client, "mood", 3, "1-5")], "skipped": True}
    assert client.post(url, json=both).json() == {"reason": "bad_value:skipped"}
    assert client.post(url, json={"readings": [r(client, "mood", 3, "1-5")]}).status_code == 200
    again = client.post(url, json={"readings": [r(client, "mood", 3, "1-5")]})
    assert again.status_code == 409 and again.json() == {"reason": "already_answered"}
    sk = morning(client)
    client.post(f"/api/prompts/{sk}/answer", json={"readings": [], "skipped": True})
    assert (
        client.post(f"/api/prompts/{sk}/answer", json={"readings": [], "skipped": True}).status_code
        == 409
    )


def test_partial_answer(client):
    pid = morning(client)
    res = client.post(
        f"/api/prompts/{pid}/answer", json={"readings": [r(client, "mood", 3, "1-5")]}
    )
    assert res.status_code == 200
