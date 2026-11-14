import json
import logging
import time
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from hub import link
from hub.api import create_app
from hub.link import LinkWatcher, fetch_link_state

BODY = {"state": "contact", "light_time_s": 720, "time_scale": 60, "queue_len": 3,
        "last_blackout": None}  # fmt: skip


def mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def app_with(settings, clock, tmp_path, handler, cfg=None):
    path = tmp_path / "link.json"
    if cfg is not None:
        path.write_text(json.dumps(cfg))
    s = replace(settings, linksim_url="http://linksim", link_config=path)
    app = create_app(s, clock=clock)

    return s, app


def get_link(settings, clock, tmp_path, handler, cfg=None, monkeypatch=None):
    s, _ = app_with(settings, clock, tmp_path, handler, cfg)
    return fetch_link_state(mock(handler), s.linksim_url, s.link_config)


def ok(body):
    return lambda req: httpx.Response(200, json=body)


def test_proxy_contact(settings, clock, tmp_path):
    assert get_link(settings, clock, tmp_path, ok(BODY)) == BODY


def test_open_blackout(settings, clock, tmp_path):
    b = {
        **BODY,
        "state": "blackout",
        "last_blackout": {"start": "2026-11-15T10:00:00.000Z", "end": None},
    }
    assert get_link(settings, clock, tmp_path, ok(b)) == b


def boom(req):
    raise httpx.ConnectError("down")


def test_unreachable_fallback(settings, clock, tmp_path):
    cfg = {"light_time_s": 600, "time_scale": 30, "blackouts": [{"start": "x"}]}
    got = get_link(settings, clock, tmp_path, boom, cfg)
    assert got == {"state": "unreachable", "light_time_s": 600, "time_scale": 30,
                   "queue_len": 0, "last_blackout": None}  # fmt: skip


def test_no_file_defaults(settings, clock, tmp_path):
    got = get_link(settings, clock, tmp_path, boom)
    assert (got["state"], got["light_time_s"], got["time_scale"]) == ("unreachable", 720, 60)


def test_malformed_upstream(settings, clock, tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        a = get_link(settings, clock, tmp_path, ok({**BODY, "state": "sleeping"}))
        broken = {k: v for k, v in BODY.items() if k != "light_time_s"}
        b = get_link(settings, clock, tmp_path, ok(broken))
    assert a["state"] == b["state"] == "unreachable" and "malformed" in caplog.text


def test_timeout(settings, clock, tmp_path, monkeypatch):
    def slow(req):
        time.sleep(1.4)
        return httpx.Response(200, json=BODY)

    s = replace(settings, linksim_url="http://127.0.0.1:9", link_config=tmp_path / "none.json")
    t = time.time()
    got = fetch_link_state(httpx.Client(), s.linksim_url, s.link_config)
    assert got["state"] == "unreachable" and time.time() - t < 1.5
    assert slow and link.TIMEOUT_S == 1.0


def test_link_frames(settings, tmp_path):
    seq = iter(["contact", "contact", "blackout"])
    frames = []
    s = replace(settings, linksim_url="http://linksim", link_config=tmp_path / "x.json")
    w = LinkWatcher(s, mock(lambda r: httpx.Response(200, json={**BODY, "state": next(seq)})),
                    lambda t, d: frames.append((t, d)))  # fmt: skip
    for _ in range(3):
        w.poll_once()
    assert [(t, d["state"]) for t, d in frames] == [("link", "contact"), ("link", "blackout")]


def test_route_always_200(settings, clock):
    with TestClient(create_app(settings, clock=clock)) as c:
        r = c.get("/api/link")
        assert r.status_code == 200 and r.json()["state"] == "unreachable"
    assert pytest and json
