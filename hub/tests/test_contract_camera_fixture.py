"""Hub half of the shared camera → hub contract fixture, data/contract/camera-reps.v1.jsonl.

camera/tests/contract-fixture.test.ts checks that the camera page still produces exactly these lines (the
messages it POSTs to /api/reps after a set). Here every line must parse, keep every field as sent, and be
stored over HTTP. A change on either side that breaks the other fails one of the two.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.contract import EXERCISES, parse_rep

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "contract" / "camera-reps.v1.jsonl"


def lines() -> list[str]:
    return FIXTURE.read_text().splitlines()


def test_every_camera_message_parses_and_keeps_its_fields() -> None:
    assert len(lines()) >= 8
    for raw in lines():
        sent = json.loads(raw)
        got = asdict(parse_rep(raw))
        assert {k: got[k] for k in sent} == sent, raw
        assert got["node"] == "camera" and got["src"] == "camera"


def test_fixture_covers_every_hub_exercise_and_a_simulated_gravity() -> None:
    reps = [parse_rep(raw) for raw in lines()]
    assert {r.exercise for r in reps} == EXERCISES
    assert any(r.g != 9.81 for r in reps)


@pytest.fixture
def client(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        yield c


def test_fixture_is_stored_over_http_then_listed_per_session(client) -> None:
    for raw in lines():
        r = client.post("/api/reps", content=raw, headers={"content-type": "application/json"})
        assert r.status_code == 201, r.text
    assert client.post("/api/reps", content=lines()[0]).status_code == 200  # a retry is a duplicate
    sessions = {json.loads(raw)["session"] for raw in lines()}
    for s in sessions:
        body = client.get("/api/reps", params={"session": s}).json()
        assert [p["camera"]["rep"] for p in body["pairs"]] == [1, 2]
