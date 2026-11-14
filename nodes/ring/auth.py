"""OAuth2 authorization code with PKCE (S256) for the ring importer (D41 §2, §3).

The vendor's URLs and the app's client id and secret come only from the environment
(RING_AUTHORIZE_URL, RING_TOKEN_URL, RING_CLIENT_ID, RING_CLIENT_SECRET, RING_REDIRECT_URI);
DATA_SOURCES.md lists their values. The token is kept in a mode-600 file under var/.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

SCOPES: tuple[str, ...] = ("heartrate", "spo2", "daily")
USER_AGENT = "habitat-ring-import/0.1"
LOOPBACK = frozenset({"127.0.0.1", "localhost"})
_ENV = {
    "client_id": "RING_CLIENT_ID",
    "client_secret": "RING_CLIENT_SECRET",
    "authorize_url": "RING_AUTHORIZE_URL",
    "token_url": "RING_TOKEN_URL",
    "redirect_uri": "RING_REDIRECT_URI",
}


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scopes: tuple[str, ...] = SCOPES


def config_from_env(env: Mapping[str, str]) -> OAuthConfig:
    missing = [key for key in _ENV.values() if not env.get(key)]
    if missing:
        raise AuthError(f"missing {', '.join(missing)} (see DATA_SOURCES.md, wearable ring)")
    return OAuthConfig(**{field: env[key] for field, key in _ENV.items()})


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)  # 64 characters from [A-Za-z0-9_-]
    return verifier, pkce_challenge(verifier)


def build_authorize_url(cfg: OAuthConfig, state: str, challenge: str) -> str:
    query = urlencode({
        "response_type": "code", "client_id": cfg.client_id, "redirect_uri": cfg.redirect_uri,
        "scope": " ".join(cfg.scopes), "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })  # fmt: skip
    return f"{cfg.authorize_url}?{query}"


def code_from_redirect(url: str, expected_state: str) -> str:
    q = {k: v[0] for k, v in parse_qs(urlsplit(url.strip()).query).items()}
    if not secrets.compare_digest(q.get("state", ""), expected_state):
        raise AuthError("state mismatch: start again with `python -m nodes.ring auth`")
    if "error" in q:
        raise AuthError(f"authorization refused: {q['error']}")
    if not q.get("code"):
        raise AuthError("no code in the redirect URL")
    return q["code"]


def _token_request(cfg: OAuthConfig, form: dict, http: httpx.Client, now: float | None) -> dict:
    body = {**form, "client_id": cfg.client_id, "client_secret": cfg.client_secret}
    res = http.post(cfg.token_url, data=body, headers={"User-Agent": USER_AGENT}, timeout=20)
    if res.status_code != 200:
        raise AuthError(f"token endpoint answered {res.status_code}: {res.text[:200]}")
    t = res.json()
    return {
        "access_token": t["access_token"],
        "refresh_token": t["refresh_token"],
        "token_type": t.get("token_type", "bearer"),
        "expires_at": (time.time() if now is None else now) + float(t.get("expires_in", 0)),
    }


def exchange_code(
    cfg: OAuthConfig, code: str, verifier: str, http: httpx.Client, *, now: float | None = None
) -> dict:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": cfg.redirect_uri,
            "code_verifier": verifier}  # fmt: skip
    return _token_request(cfg, form, http, now)


def refresh_token(
    cfg: OAuthConfig, refresh: str, http: httpx.Client, *, now: float | None = None
) -> dict:
    """Refresh tokens are single-use: the caller must save the returned token at once."""
    return _token_request(cfg, {"grant_type": "refresh_token", "refresh_token": refresh}, http, now)


def save_token(path: Path, tok: dict) -> None:
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps(tok).encode())
    finally:
        os.close(fd)
    os.replace(tmp, path)


def load_token(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise AuthError(f"no token at {path}: run `python -m nodes.ring auth` first")
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise AuthError(f"{path} has mode {mode:o}; it must be 600 (chmod 600 {path})")
    return json.loads(path.read_text(encoding="utf-8"))


def is_loopback_redirect(redirect_uri: str) -> bool:
    parts = urlsplit(redirect_uri)
    return parts.scheme == "http" and parts.hostname in LOOPBACK and bool(parts.port)


class _ExclusiveServer(HTTPServer):
    # No SO_REUSEADDR: binding fails if any other program already listens on this port, so an
    # authorization code can never be delivered to someone else's server.
    allow_reuse_address = False


def wait_for_redirect(
    redirect_uri: str, timeout_s: float = 300, on_ready: Callable[[], None] | None = None
) -> str:
    """Serve one GET on the loopback redirect URI and return the full URL it was called with.

    The port is bound first; `on_ready` (open the browser) runs only once the port is ours.
    """
    parts = urlsplit(redirect_uri)
    if not is_loopback_redirect(redirect_uri):
        raise AuthError(f"{redirect_uri} is not a local http redirect; paste the URL instead")
    got: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urlsplit(self.path).path != (parts.path or "/"):
                self.send_error(404)
                return
            got.append(f"http://{parts.netloc}{self.path}")
            body = b"Ring authorization received. You can close this tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return  # keep the code out of the terminal log

    try:
        server = _ExclusiveServer(("127.0.0.1", parts.port), Handler)
    except OSError as e:
        raise AuthError(
            f"port {parts.port} is in use by another program ({e.strerror}); register a free port "
            "as the redirect URI and set RING_REDIRECT_URI to match"
        ) from None
    deadline = time.monotonic() + timeout_s
    with server:
        if on_ready is not None:
            on_ready()
        server.timeout = 0.5
        while not got and time.monotonic() < deadline:
            server.handle_request()
    if not got:
        raise AuthError(f"no redirect within {timeout_s:.0f} s")
    return got[0]
