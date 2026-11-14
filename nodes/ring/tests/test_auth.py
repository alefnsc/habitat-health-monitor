"""OAuth2 authorization code with PKCE for the ring importer (D41 §3). No real network."""

from __future__ import annotations

import socket
import threading
import urllib.request
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from nodes.ring.auth import (
    SCOPES,
    USER_AGENT,
    AuthError,
    OAuthConfig,
    build_authorize_url,
    code_from_redirect,
    config_from_env,
    exchange_code,
    load_token,
    make_pkce,
    pkce_challenge,
    refresh_token,
    save_token,
    wait_for_redirect,
)

TOKEN_URL = "https://auth.example.test/oauth/token"
CFG = OAuthConfig(
    client_id="cid", client_secret="csecret",
    authorize_url="https://auth.example.test/oauth/authorize", token_url=TOKEN_URL,
    redirect_uri="http://127.0.0.1:8799/callback",
)  # fmt: skip
ENV = {"RING_CLIENT_ID": "cid", "RING_CLIENT_SECRET": "csecret",
       "RING_AUTHORIZE_URL": CFG.authorize_url, "RING_TOKEN_URL": TOKEN_URL,
       "RING_REDIRECT_URI": CFG.redirect_uri}  # fmt: skip
NOW = 1_763_130_000.0


def test_config_from_env_and_missing_keys():
    assert config_from_env(ENV) == CFG
    with pytest.raises(AuthError, match="RING_CLIENT_SECRET"):
        config_from_env({k: v for k, v in ENV.items() if k != "RING_CLIENT_SECRET"})


def test_pkce_vector_from_the_public_docs_and_fresh_pairs():
    verifier = "QUW2bsoMYITWSSPUgCDEc4CXCBfcVyu8TkujreHe8CXP4K4d4463gRztuxfo96YP"
    assert pkce_challenge(verifier) == "43Kb1gELSIjkvwzrPtAg0Lz2HqCG3BtS_SUMAQhjv7c"
    v1, c1 = make_pkce()
    v2, _ = make_pkce()
    assert 43 <= len(v1) <= 128 and v1 != v2 and c1 == pkce_challenge(v1) and "=" not in c1


def test_authorize_url_parameters():
    url = build_authorize_url(CFG, "st4te", "chall")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == CFG.authorize_url
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q == {"response_type": "code", "client_id": "cid", "redirect_uri": CFG.redirect_uri,
                 "scope": "heartrate spo2 daily", "state": "st4te", "code_challenge": "chall",
                 "code_challenge_method": "S256"}  # fmt: skip
    assert SCOPES == ("heartrate", "spo2", "daily")


def test_code_from_redirect_checks_state_and_errors():
    assert code_from_redirect(CFG.redirect_uri + "?code=abc&state=s1", "s1") == "abc"
    with pytest.raises(AuthError, match="state"):
        code_from_redirect(CFG.redirect_uri + "?code=abc&state=evil", "s1")
    with pytest.raises(AuthError, match="access_denied"):
        code_from_redirect(CFG.redirect_uri + "?error=access_denied&state=s1", "s1")
    with pytest.raises(AuthError, match="code"):
        code_from_redirect(CFG.redirect_uri + "?state=s1", "s1")


@respx.mock
def test_exchange_code_posts_the_form_and_normalises_the_token():
    tok_json = {"token_type": "bearer", "access_token": "AT", "expires_in": 86400, "refresh_token": "RT"}
    route = respx.post(TOKEN_URL).respond(200, json=tok_json)
    with httpx.Client() as http:
        tok = exchange_code(CFG, "abc", "verif", http, now=NOW)
    assert tok == {"access_token": "AT", "refresh_token": "RT", "token_type": "bearer",
                   "expires_at": NOW + 86400}  # fmt: skip
    req = route.calls.last.request
    form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
    assert form == {"grant_type": "authorization_code", "code": "abc", "redirect_uri": CFG.redirect_uri,
                    "client_id": "cid", "client_secret": "csecret", "code_verifier": "verif"}  # fmt: skip
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert req.headers["user-agent"] == USER_AGENT


@respx.mock
def test_refresh_and_token_endpoint_errors():
    route = respx.post(TOKEN_URL).respond(
        200, json={"token_type": "bearer", "access_token": "AT2", "expires_in": 60, "refresh_token": "RT2"}
    )
    with httpx.Client() as http:
        tok = refresh_token(CFG, "RT1", http, now=NOW)
        assert (tok["access_token"], tok["refresh_token"]) == ("AT2", "RT2")
        form = {k: v[0] for k, v in parse_qs(route.calls.last.request.content.decode()).items()}
        assert form == {"grant_type": "refresh_token", "refresh_token": "RT1", "client_id": "cid",
                        "client_secret": "csecret"}  # fmt: skip
        route.respond(400, json={"error": "invalid_grant"})
        with pytest.raises(AuthError, match="400"):
            refresh_token(CFG, "RT1", http, now=NOW)


def test_token_file_is_private(tmp_path):
    path = tmp_path / "var" / "ring" / "token.json"
    tok = {"access_token": "AT", "refresh_token": "RT", "token_type": "bearer", "expires_at": NOW}
    save_token(path, tok)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert load_token(path) == tok
    path.chmod(0o644)
    with pytest.raises(AuthError, match="600"):
        load_token(path)
    with pytest.raises(AuthError, match="auth"):
        load_token(tmp_path / "nope.json")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_wait_for_redirect_catches_the_callback_on_loopback():
    uri = f"http://127.0.0.1:{_free_port()}/callback"
    got: list[str] = []
    t = threading.Thread(target=lambda: got.append(wait_for_redirect(uri, timeout_s=10)))
    t.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(uri + "?code=xyz&state=s9", timeout=2) as r:
                body = r.read().decode()
            break
        except OSError:
            threading.Event().wait(0.05)
    t.join(10)
    assert "close this tab" in body
    assert code_from_redirect(got[0], "s9") == "xyz"


def test_wait_for_redirect_refuses_a_port_someone_else_holds():
    """If another program listens on the callback port, stop before the browser ever opens."""
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        uri = f"http://127.0.0.1:{other.getsockname()[1]}/callback"
        opened: list[bool] = []
        with pytest.raises(AuthError, match="in use"):
            wait_for_redirect(uri, timeout_s=1, on_ready=lambda: opened.append(True))
        assert opened == []


def test_wait_for_redirect_refuses_a_non_local_redirect():
    with pytest.raises(AuthError, match="local"):
        wait_for_redirect("https://example.test/callback", timeout_s=1)
