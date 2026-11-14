"""Replay a recorded ring pull into a real hub app over HTTP, with no network (D41 §3, §8)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.config import load_settings
from nodes.ring.__main__ import main
from nodes.ring.hubpost import post_readings

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data" / "replay" / "ring-synthetic-nights.jsonl"


class Clock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 14, 15, 0, tzinfo=UTC)


@pytest.fixture
def hub(tmp_path):
    missing = tmp_path / "missing"
    base = load_settings({})
    settings = replace(
        base, db_path=tmp_path / "hub.db", linksim_url="", mqtt_host="",
        features=base.features - {"nasa", "iss"}, console_dist=missing / "console",
        camera_dist=missing / "camera", link_config=missing / "link.json",
        thresholds_path=ROOT / "data" / "thresholds.json",
        guidance_path=ROOT / "data" / "guidance.json",
    )  # fmt: skip
    with TestClient(create_app(settings, clock=Clock())) as c:
        yield c


def rows(client: TestClient, ind: str) -> list[dict]:
    r = client.get("/api/readings", params={"ind": ind, "limit": 1000})
    assert r.status_code == 200
    body = r.json()
    return body["readings"] if isinstance(body, dict) else body


@respx.mock(assert_all_called=False)
def test_replay_cli_posts_the_fixture_with_no_network(hub, capsys):
    # respx blocks every real request: only the in-process TestClient hub is reachable.
    assert main(["replay", str(FIXTURE)], http=hub) == 0
    out = capsys.readouterr().out
    assert "stored 98" in out and "rejected 0" in out
    hr = rows(hub, "hr")
    assert len(hr) == 94
    assert {(r["node"], r["src"], r["dev"], r["crew"], r["boot"]) for r in hr} == {
        ("ring-1", "replay", "RING", "crew-b", 2)
    }
    (last_night,) = [r for r in rows(hub, "sleep_h") if r["val"] == 6.6]
    # replay age = pulled_at (12:00Z) - bedtime_end (09:40Z) = 2 h 20 min; the hub clock is 15:00Z
    assert last_night["measured_at"] == "2026-11-14T12:40:00.000Z"
    assert len(rows(hub, "spo2")) == 2
    assert rows(hub, "skin_temp") == []


def test_second_replay_is_all_duplicates(hub, capsys):
    assert main(["replay", str(FIXTURE)], http=hub) == 0
    capsys.readouterr()
    assert main(["replay", str(FIXTURE)], http=hub) == 0
    assert "stored 0, duplicate 98, rejected 0" in capsys.readouterr().out


def test_post_readings_counts_rejects(hub):
    good = {"v": 1, "node": "ring-1", "boot": 2, "seq": 9, "age_ms": 0, "ind": "hr", "val": 55,
            "unit": "bpm", "src": "replay", "dev": "RING", "q": ["ok"], "crew": "crew-b"}  # fmt: skip
    bad = {**good, "seq": 10, "unit": "mmHg"}
    assert post_readings([good, good, bad], hub) == {"stored": 1, "duplicate": 1, "rejected": 1}


def test_post_readings_survives_an_unreachable_hub():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(refuse)
    with (
        httpx.Client(base_url="http://127.0.0.1:9", transport=transport) as c,
        pytest.raises(httpx.ConnectError),
    ):
        post_readings([{"v": 1}], c)
