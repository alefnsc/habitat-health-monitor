import json
from datetime import UTC, datetime, timedelta
from urllib.request import urlopen

import httpx
import pytest

from linksim.config import LinkConfig
from linksim.engine import LinkEngine
from linksim.io import LinkDown, fetch_outbox, load_cursor, post_ground, save_cursor, step
from linksim.status import serve_status

BASE = datetime(2026, 11, 15, 13, 0, 0, tzinfo=UTC)


def wall(t: float) -> str:
    return (BASE + timedelta(seconds=t)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _engine() -> LinkEngine:
    return LinkEngine(LinkConfig(720.0, 60.0, []), 0.0, wall)


def _items(ids):
    return [
        {"id": i, "kind": "reading", "created_at": wall(i), "payload": {"ind": "hr", "val": 60 + i}}
        for i in ids
    ]


def _client(handler, base="http://test"):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=base)


def test_fetch_params():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"items": _items([42, 43]), "last_id": 43})

    out = fetch_outbox(_client(handler), "http://hub", 41, 500)
    assert seen[0].url.path == "/api/outbox"
    assert dict(seen[0].url.params) == {"after": "41", "limit": "500"}
    assert [i.id for i in out] == [42, 43]
    assert out[0].payload == {"ind": "hr", "val": 102}


def test_fetch_empty():
    c = _client(lambda r: httpx.Response(200, json={"items": [], "last_id": 43}))
    assert fetch_outbox(c, "http://hub", 43, 500) == []


def test_fetch_hub_down():
    def handler(req):
        raise httpx.ConnectError("down")

    assert fetch_outbox(_client(handler), "http://hub", 0, 500) == []


def test_post_ok():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"max_id": 3, "stored": 3})

    from linksim.engine import OutboxItem

    items = [OutboxItem(**d) for d in _items([1, 2, 3])]
    assert post_ground(_client(handler), "http://ground", None, items) == 3
    assert set(bodies[0]) == {"beacon", "items"}
    assert [i["id"] for i in bodies[0]["items"]] == [1, 2, 3]


def test_post_timeout():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LinkDown):
        post_ground(_client(handler), "http://ground", None, [])


def test_post_500():
    with pytest.raises(LinkDown):
        post_ground(_client(lambda r: httpx.Response(500)), "http://ground", None, [])


def test_cursor_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    assert load_cursor(p) == 0
    save_cursor(p, 17)
    assert load_cursor(p) == 17
    assert json.loads(p.read_text()) == {"delivered_id": 17}


class Hub:
    def __init__(self):
        self.afters = []

    def __call__(self, req):
        after = int(req.url.params["after"])
        self.afters.append(after)
        items = _items([1, 2, 3]) if after == 0 else []
        return httpx.Response(200, json={"items": items, "last_id": 3})


class Ground:
    def __init__(self, fail_times=()):
        self.fail_times = set(fail_times)
        self.clock = 0.0
        self.calls = []
        self.stored = []

    def __call__(self, req):
        body = json.loads(req.content)
        self.calls.append(self.clock)
        if self.clock in self.fail_times:
            return httpx.Response(503)
        for i in body["items"]:
            if i["id"] not in self.stored:
                self.stored.append(i["id"])
        return httpx.Response(200, json={"max_id": max(self.stored, default=None), "stored": 0})


def test_step_flow(tmp_path):
    e, hub, ground = _engine(), Hub(), Ground()
    cursor = tmp_path / "state.json"
    hc, gc = _client(hub), _client(ground)
    step(e, hc, gc, cursor, 0.0)
    assert hub.afters == [0] and ground.calls == []
    ground.clock = 12.0
    step(e, hc, gc, cursor, 12.0)
    assert ground.stored == [1, 2, 3]
    assert load_cursor(cursor) == 3
    assert hub.afters[-1] == 3


def test_step_ground_down_then_up(tmp_path):
    e, hub, ground = _engine(), Hub(), Ground(fail_times={12.0, 13.0})
    cursor = tmp_path / "state.json"
    hc, gc = _client(hub), _client(ground)
    step(e, hc, gc, cursor, 0.0)
    for t in (12.0, 13.0, 14.0):
        ground.clock = t
        step(e, hc, gc, cursor, t)
        if t == 13.0:
            assert e.snapshot(t).state == "unreachable"
    assert ground.stored == [1, 2, 3]
    assert e.snapshot(14.0).state == "contact"


def test_status_endpoint():
    e = _engine()
    server = serve_status(e, "127.0.0.1", 0, lambda: 5.0)
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/link/state", timeout=3) as r:
            assert r.status == 200
            body = json.loads(r.read())
    finally:
        server.shutdown()
    assert set(body) == {"state", "light_time_s", "time_scale", "queue_len", "last_blackout"}
    assert body["light_time_s"] == 720 and body["time_scale"] == 60
