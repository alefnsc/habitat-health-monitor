"""python -m nodes.ring {auth,pull,replay}: the wearable ring importer (D41).

  auth                      sign in once (OAuth2 code + PKCE); saves var/ring/token.json, mode 600
  pull [--days N]           fetch from the cloud, save the raw pull, post as src hobby with its true age
  replay FILE               post recorded pulls as src replay (no cloud access)

Settings come from RING_* environment variables, or from .env for any that are unset.
The habitat core never calls the cloud: ring vitals are a delayed cloud sync.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
import webbrowser
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from nodes.ring.auth import (
    AuthError,
    build_authorize_url,
    code_from_redirect,
    config_from_env,
    exchange_code,
    is_loopback_redirect,
    make_pkce,
    save_token,
    wait_for_redirect,
)
from nodes.ring.client import RingApiError, RingClient
from nodes.ring.hubpost import post_readings
from nodes.ring.mapper import map_pull
from nodes.ring.records import KIND, append_record, load_records

DEFAULT_HUB = "http://127.0.0.1:8000"
DEFAULT_TOKEN = "var/ring/token.json"
DEFAULT_PULLS = "var/ring/pulls.jsonl"


def load_env(path: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """RING_* settings: the environment wins, .env fills the rest. Nothing else is read."""
    out = {k: v for k, v in environ.items() if k.startswith("RING_")}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, sep, val = line.strip().partition("=")
            if sep and key.startswith("RING_") and key not in out:
                out[key] = val.strip().strip("'\"")
    return out


def _report(verb: str, n: int, counts: dict[str, int], skipped: Counter[str]) -> None:
    print(
        f"{verb} {n} record(s): stored {counts['stored']}, duplicate {counts['duplicate']}, "
        f"rejected {counts['rejected']}"
    )
    if skipped:
        print("skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(skipped.items())))


def _replay(args: argparse.Namespace, http: httpx.Client) -> int:
    records = load_records(Path(args.file))
    totals = {"stored": 0, "duplicate": 0, "rejected": 0}
    skipped: Counter[str] = Counter()
    for rec in records:
        res = map_pull(rec, mode="replay")
        skipped.update(res.skipped)
        for k, v in post_readings(res.readings, http).items():
            totals[k] += v
    _report("replayed", len(records), totals, skipped)
    return 0 if totals["rejected"] == 0 else 1


def _auth(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    cfg = config_from_env(env)
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(24)
    url = build_authorize_url(cfg, state, challenge)
    print("Sign in with the ring account and allow heartrate, spo2 and daily:\n" + url)
    if not args.no_browser:
        webbrowser.open(url)
    if is_loopback_redirect(cfg.redirect_uri):
        print(f"Waiting for the redirect on {cfg.redirect_uri} ...")
        redirect = wait_for_redirect(cfg.redirect_uri)
    else:
        redirect = input("Paste the full URL the browser was sent to: ")
    code = code_from_redirect(redirect, state)
    with httpx.Client() as http:
        tok = exchange_code(cfg, code, verifier, http)
    save_token(Path(args.token), tok)
    print(f"Token saved to {args.token} (mode 600). Next: python -m nodes.ring pull")
    return 0


def _pull(args: argparse.Namespace, env: Mapping[str, str], http: httpx.Client) -> int:
    cfg = config_from_env(env)
    base = env.get("RING_API_BASE")
    if not base:
        raise AuthError("missing RING_API_BASE (see DATA_SOURCES.md, wearable ring)")
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(days=args.days)
    with httpx.Client() as api:
        docs = RingClient(cfg, base, Path(args.token), api).fetch_window(start, end)
    record = {"kind": KIND, "v": 1, "pulled_at": end.isoformat(),
              "window": {"start": start.isoformat(), "end": end.isoformat()}, **docs}  # fmt: skip
    append_record(Path(args.pulls), record)
    res = map_pull(record, mode="pull", now_ms=int(time.time() * 1000))
    print(f"saved the raw pull to {args.pulls}")
    if args.dry_run:
        print(f"dry run: {len(res.readings)} reading(s) mapped, nothing posted")
        if res.skipped:
            print("skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(res.skipped.items())))
        return 0
    counts = post_readings(res.readings, http)
    _report("pulled", 1, counts, Counter(res.skipped))
    return 0 if counts["rejected"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m nodes.ring", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("auth", help="sign in once and save the token")
    au.add_argument("--token", default=DEFAULT_TOKEN)
    au.add_argument("--no-browser", action="store_true", help="print the URL, do not open it")
    pu = sub.add_parser("pull", help="fetch, save the raw pull, post as src hobby")
    pu.add_argument("--days", type=int, default=2, help="how many days back (default 2)")
    pu.add_argument("--token", default=DEFAULT_TOKEN)
    pu.add_argument("--pulls", default=DEFAULT_PULLS, help=f"raw pulls file (default {DEFAULT_PULLS})")
    pu.add_argument("--dry-run", action="store_true", help="fetch and save, but post nothing")
    rp = sub.add_parser("replay", help="post recorded pulls as src replay")
    rp.add_argument("file", help="a pulls JSONL file, such as data/replay/ring-synthetic-nights.jsonl")
    for p in (pu, rp):
        p.add_argument("--hub", default=DEFAULT_HUB, help=f"hub base URL (default {DEFAULT_HUB})")
    return ap


def main(
    argv: list[str] | None = None,
    *,
    http: httpx.Client | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    env = load_env(Path(".env"), os.environ) if env is None else env
    try:
        if args.cmd == "auth":
            return _auth(args, env)
        if http is None:
            with httpx.Client(base_url=args.hub, timeout=10) as client:
                return main(argv, http=client, env=env)
        if args.cmd == "replay":
            return _replay(args, http)
        return _pull(args, env, http)
    except (AuthError, RingApiError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
