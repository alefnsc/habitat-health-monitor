import json
from datetime import UTC, datetime

import pytest

from hub.nasa.isslive import IssItemUpdate, IssLiveState
from hub.nasa.isslive_client import IssLiveClient, record_capture


class FakeUpdate:
    def __init__(self, item, fields):
        self._item, self._fields = item, fields

    def getItemName(self):
        return self._item

    def getValue(self, name):
        return self._fields.get(name)


def test_listener_feeds_state():
    state = IssLiveState()
    client = IssLiveClient(["USLAB000058"], state)
    client.listener.onItemUpdate(
        FakeUpdate(
            "USLAB000058", {"TimeStamp": "7630.65", "Value": "759.26", "Status.Class": "Normal"}
        )
    )
    u = state.latest()["USLAB000058"]
    assert u.val == 759.26 and u.status_class == "Normal"


def test_status_listener_tracks_connection():
    state = IssLiveState()
    client = IssLiveClient(["USLAB000058"], state)
    client.status_listener.onStatusChange("CONNECTED:WS-STREAMING")
    assert state.connected is True and state.last_connected_at is not None
    client.status_listener.onStatusChange("DISCONNECTED:WILL-RETRY")
    assert state.connected is False


def test_never_subscribes_time_item():
    with pytest.raises(ValueError):
        IssLiveClient(["USLAB000058", "TIME_000001"], IssLiveState())


def test_record_capture_lines(tmp_path):
    t = datetime(2026, 11, 14, 12, tzinfo=UTC)
    ups = [IssItemUpdate("USLAB000058", 759.0 + i, 7620.5, t, "Normal", t) for i in range(3)]
    p = tmp_path / "cap.jsonl"
    assert record_capture(p, ups) == 3
    lines = [json.loads(x) for x in p.read_text().splitlines()]
    assert len(lines) == 3
    for ln in lines:
        assert {"item", "val", "ts", "status_class", "received_at"} <= set(ln)
