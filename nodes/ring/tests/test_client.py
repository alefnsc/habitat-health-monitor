"""Ring API client and the auth/pull commands (D41 §3). The vendor API is mocked with respx."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.config import load_settings
from nodes.ring import __main__ as cli
from nodes.ring.auth import USER_AGENT, AuthError, OAuthConfig, load_token, save_token
from nodes.ring.client import RingApiError, RingClient
from nodes.ring.records import load_records

API = "https://api.example.test"
TOKEN_URL = "https://auth.example.test/oauth/token"
CFG = OAuthConfig("cid", "csecret", "https://auth.example.test/oauth/authorize", TOKEN_URL,
                  "http://127.0.0.1:8799/callback")  # fmt: skip
ENV = {"RING_CLIENT_ID": "cid", "RING_CLIENT_SECRET": "csecret", "RING_AUTHORIZE_URL": CFG.authorize_url,
       "RING_TOKEN_URL": TOKEN_URL, "RING_REDIRECT_URI": CFG.redirect_uri, "RING_API_BASE": API}  # fmt: skip
NOW = datetime(2026, 11, 14, 15, 0, tzinfo=UTC).timestamp()
HR = f"{API}/v2/usercollection/heartrate"
SLEEP = f"{API}/v2/usercollection/sleep"
SPO2 = f"{API}/v2/usercollection/daily_spo2"


def tok(access: str = "AT1", refresh: str = "RT1", expires_at: float = NOW + 3600) -> dict:
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_at": expires_at}


def hr_row(iso: str, bpm: int, source: str = "sleep") -> dict:
    ms = int(datetime.fromisoformat(iso).timestamp() * 1000)
    return {"timestamp": iso, "timestamp_unix": ms, "bpm": bpm, "source": source}


@pytest.fixture
def token_path(tmp_path) -> Path:
    p = tmp_path / "var" / "ring" / "token.json"
    # valid for the fixed test clock and for the real clock the CLI uses
    save_token(p, tok(expires_at=max(NOW, time.time()) + 3600))
    return p


@respx.mock
def test_get_all_follows_next_token_and_sends_bearer_and_user_agent(token_path):
    route = respx.get(HR).mock(side_effect=[
        httpx.Response(200, json={"data": [{"n": 1}], "next_token": "p2"}),
        httpx.Response(200, json={"data": [{"n": 2}], "next_token": None}),
    ])  # fmt: skip
    with httpx.Client() as http:
        c = RingClient(CFG, API, token_path, http, clock=lambda: NOW)
        assert c.get_all("/v2/usercollection/heartrate", {"start_datetime": "x"}) == [{"n": 1}, {"n": 2}]
    first, second = (call.request for call in route.calls)
    assert first.headers["authorization"] == "Bearer AT1"
    assert first.headers["user-agent"] == USER_AGENT
    assert "next_token" not in parse_qs(urlsplit(str(first.url)).query)
    assert parse_qs(urlsplit(str(second.url)).query)["next_token"] == ["p2"]


@respx.mock
def test_401_refreshes_once_saves_the_new_refresh_token_and_retries(token_path):
    respx.post(TOKEN_URL).respond(200, json={"access_token": "AT2", "refresh_token": "RT2",
                                              "token_type": "bearer", "expires_in": 86400})  # fmt: skip
    route = respx.get(SLEEP).mock(side_effect=[
        httpx.Response(401, json={"detail": "expired"}),
        httpx.Response(200, json={"data": [{"id": "s"}], "next_token": None}),
    ])  # fmt: skip
    with httpx.Client() as http:
        c = RingClient(CFG, API, token_path, http, clock=lambda: NOW)
        assert c.get_all("/v2/usercollection/sleep", {}) == [{"id": "s"}]
    assert route.calls.last.request.headers["authorization"] == "Bearer AT2"
    assert load_token(token_path)["refresh_token"] == "RT2"


@respx.mock
def test_second_401_and_429_are_errors(token_path):
    respx.post(TOKEN_URL).respond(200, json={"access_token": "AT2", "refresh_token": "RT2", "expires_in": 60})
    respx.get(SLEEP).respond(401)
    respx.get(SPO2).respond(429, headers={"X-RateLimit-Tier": "token"})
    with httpx.Client() as http:
        c = RingClient(CFG, API, token_path, http, clock=lambda: NOW)
        with pytest.raises(AuthError, match="401"):
            c.get_all("/v2/usercollection/sleep", {})
        with pytest.raises(RingApiError, match="429"):
            c.get_all("/v2/usercollection/daily_spo2", {})


@respx.mock
def test_expired_token_is_refreshed_before_the_first_call(tmp_path):
    path = tmp_path / "token.json"
    save_token(path, tok(expires_at=NOW - 5))
    refresh = respx.post(TOKEN_URL).respond(200, json={"access_token": "AT9", "refresh_token": "RT9",
                                                        "expires_in": 86400})  # fmt: skip
    respx.get(HR).respond(200, json={"data": [], "next_token": None})
    with httpx.Client() as http:
        RingClient(CFG, API, path, http, clock=lambda: NOW).get_all("/v2/usercollection/heartrate", {})
    assert refresh.called and load_token(path)["access_token"] == "AT9"


@respx.mock
def test_fetch_window_queries_the_three_endpoints(token_path):
    hr = respx.get(HR).respond(200, json={"data": [1], "next_token": None})
    sl = respx.get(SLEEP).respond(200, json={"data": [2], "next_token": None})
    sp = respx.get(SPO2).respond(200, json={"data": [3], "next_token": None})
    start = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    end = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)
    with httpx.Client() as http:
        got = RingClient(CFG, API, token_path, http, clock=lambda: NOW).fetch_window(start, end)
    assert got == {"heartrate": [1], "sleep": [2], "daily_spo2": [3]}
    q = parse_qs(urlsplit(str(hr.calls.last.request.url)).query)
    assert q == {"start_datetime": ["2026-11-12T15:00:00+00:00"], "end_datetime": ["2026-11-14T15:00:00+00:00"]}
    for route in (sl, sp):
        q = parse_qs(urlsplit(str(route.calls.last.request.url)).query)
        assert q == {"start_date": ["2026-11-12"], "end_date": ["2026-11-15"]}


@pytest.fixture
def hub(tmp_path):
    missing = tmp_path / "missing"
    base = load_settings({})
    settings = replace(
        base, db_path=tmp_path / "hub.db", linksim_url="", mqtt_host="",
        features=base.features - {"nasa", "iss"}, console_dist=missing / "c",
        camera_dist=missing / "k", link_config=missing / "l.json",
    )  # fmt: skip
    with TestClient(create_app(settings)) as c:
        yield c


def _mock_vendor_night() -> None:
    respx.get(HR).respond(200, json={"data": [hr_row("2026-11-14T08:00:00+00:00", 54),
                                              hr_row("2026-11-14T13:00:00+00:00", 95, "awake")],
                                     "next_token": None})  # fmt: skip
    respx.get(SLEEP).respond(200, json={"data": [{
        "id": "s1", "day": "2026-11-14", "bedtime_start": "2026-11-14T02:00:00+00:00",
        "bedtime_end": "2026-11-14T09:30:00+00:00", "total_sleep_duration": 25200, "type": "long_sleep"}],
        "next_token": None})  # fmt: skip
    respx.get(SPO2).respond(200, json={"data": [{"id": "o1", "day": "2026-11-14",
                                                 "spo2_percentage": {"average": 97.3}}],
                                       "next_token": None})  # fmt: skip


@respx.mock
def test_pull_saves_the_raw_record_privately_and_posts_hobby_readings(hub, token_path, tmp_path, capsys):
    _mock_vendor_night()
    pulls = tmp_path / "var" / "ring" / "pulls.jsonl"
    argv = ["pull", "--days", "1", "--token", str(token_path), "--pulls", str(pulls)]
    assert cli.main(argv, http=hub, env=ENV) == 0
    out = capsys.readouterr().out
    assert "stored 3" in out and "hr_source_awake 1" in out
    (rec,) = load_records(pulls)
    assert rec["heartrate"][0]["bpm"] == 54 and pulls.stat().st_mode & 0o777 == 0o600
    rows = hub.get("/api/readings", params={"ind": "sleep_h"}).json()
    rows = rows["readings"] if isinstance(rows, dict) else rows
    assert [(r["src"], r["boot"], r["val"], r["crew"]) for r in rows] == [("hobby", 1, 7.0, "crew-b")]
    # replaying that raw pull later goes in as src replay (boot 2), next to the hobby rows
    assert cli.main(["replay", str(pulls)], http=hub) == 0
    assert "stored 3" in capsys.readouterr().out


@respx.mock
def test_pull_dry_run_records_but_posts_nothing(token_path, tmp_path, capsys):
    _mock_vendor_night()
    pulls = tmp_path / "pulls.jsonl"

    def no_post(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run must not post")

    with httpx.Client(base_url="http://hub.test", transport=httpx.MockTransport(no_post)) as hub_http:
        argv = ["pull", "--dry-run", "--token", str(token_path), "--pulls", str(pulls)]
        assert cli.main(argv, http=hub_http, env=ENV) == 0
    assert len(load_records(pulls)) == 1
    assert "dry run: 3 reading(s) mapped, nothing posted" in capsys.readouterr().out


@respx.mock
def test_auth_command_runs_the_code_flow_and_saves_a_private_token(tmp_path, monkeypatch, capsys):
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)

    def fake_wait(redirect_uri: str, timeout_s: float = 300) -> str:
        state = parse_qs(urlsplit(opened[0]).query)["state"][0]
        return f"{redirect_uri}?code=C0DE&state={state}"

    monkeypatch.setattr(cli, "wait_for_redirect", fake_wait)
    exch = respx.post(TOKEN_URL).respond(200, json={"access_token": "AT", "refresh_token": "RT",
                                                     "expires_in": 86400})  # fmt: skip
    path = tmp_path / "var" / "ring" / "token.json"
    assert cli.main(["auth", "--token", str(path)], env=ENV) == 0
    form = {k: v[0] for k, v in parse_qs(exch.calls.last.request.content.decode()).items()}
    assert form["code"] == "C0DE" and len(form["code_verifier"]) >= 43
    assert load_token(path)["refresh_token"] == "RT" and path.stat().st_mode & 0o777 == 0o600
    out = capsys.readouterr().out
    assert "AT" not in out.split() and "RT" not in out.split()  # never print the token


def test_dotenv_fills_only_missing_ring_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RING_CLIENT_ID=from-file\nRING_API_BASE=https://file.test\nOTHER=x\n# c\n")
    got = cli.load_env(env_file, {"RING_CLIENT_ID": "from-env"})
    assert got["RING_CLIENT_ID"] == "from-env" and got["RING_API_BASE"] == "https://file.test"
    assert "OTHER" not in got


def test_main_reports_missing_config_without_a_traceback(tmp_path, capsys):
    assert cli.main(["pull", "--token", str(tmp_path / "t.json")], env={}) == 2
    assert "missing RING_" in capsys.readouterr().err
