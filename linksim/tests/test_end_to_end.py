"""In-process link runs: fake hub, real engine and I/O, real receiver app. No sockets."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from receiver.app import create_app

from linksim.config import load_config
from linksim.engine import LinkEngine
from linksim.io import step

HERE = Path(__file__).resolve().parent.parent
BASE = datetime(2026, 11, 15, 13, 0, 0, tzinfo=UTC)


def wall(t: float) -> str:
    return (BASE + timedelta(seconds=t)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Rig:
    def __init__(self, tmp_path, config: str, down=None):
        self.t = 0.0
        self.down = down  # (from_t, to_t) when the ground refuses connections
        self.posts: list[tuple[float, list[int]]] = []
        self.receiver = TestClient(create_app(tmp_path / "ground.db", None))
        self.engine = LinkEngine(load_config(HERE / config), 0.0, wall)
        self.cursor = tmp_path / "state.json"
        self.hub = httpx.Client(transport=httpx.MockTransport(self._hub), base_url="http://hub")
        self.ground = httpx.Client(
            transport=httpx.MockTransport(self._ground), base_url="http://ground"
        )

    def _hub(self, req: httpx.Request) -> httpx.Response:
        after = int(req.url.params["after"])
        limit = int(req.url.params["limit"])
        visible = min(100, int(self.t) + 1)  # item k appears at t = k - 1
        items = [
            {"id": k, "kind": "reading", "created_at": wall(k - 1), "payload": {"k": k}}
            for k in range(after + 1, visible + 1)
        ][:limit]
        return httpx.Response(200, json={"items": items, "last_id": visible})

    def _ground(self, req: httpx.Request) -> httpx.Response:
        if self.down and self.down[0] <= self.t < self.down[1]:
            raise httpx.ConnectError("unplugged")
        body = json.loads(req.content)
        self.posts.append((self.t, [i["id"] for i in body["items"]]))
        r = self.receiver.post(req.url.path, json=body)
        assert r.status_code == 200, r.text
        return httpx.Response(r.status_code, json=r.json())

    def run(self, until: float = 200.0):
        for n in range(int(until / 0.25) + 1):
            self.t = n * 0.25
            step(self.engine, self.hub, self.ground, self.cursor, self.t)
            yield self.t

    def summary(self) -> dict:
        return self.receiver.get("/ground/summary").json()


def test_end_to_end_blackout(tmp_path):
    rig = Rig(tmp_path, "link.demo.json")
    for _ in rig.run():
        pass
    times = [t for t, _ in rig.posts]
    assert max(t for t in times if t < 42.25) <= 42.0
    assert not [t for t in times if 42.25 <= t <= 71.75]
    first_after = next((t, ids) for t, ids in rig.posts if t >= 72.0)
    assert first_after[0] == 72.0
    assert first_after[1] == list(range(31, 62))
    s = rig.summary()
    assert (s["stored"], s["min_id"], s["max_id"], s["missing_ids"]) == (100, 1, 100, 0)


def test_end_to_end_unplug(tmp_path):
    rig = Rig(tmp_path, "link.json", down=(20.0, 50.0))
    for t in rig.run():
        state = rig.engine.snapshot(t).state
        if 20.0 <= t < 50.0:
            assert state == "unreachable", t
            if t == 49.75:
                assert rig.engine.snapshot(t).queue_len >= 30
        elif t >= 50.0:
            assert state == "contact", t
    s = rig.summary()
    assert s["stored"] == 100 and s["missing_ids"] == 0
