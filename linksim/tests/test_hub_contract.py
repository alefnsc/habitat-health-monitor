"""Contract check of the hub outbox (resolution D1, alert shape D3) against a recorded sample.

The fixture was recorded from the real hub (GET /api/outbox, H12):
  curl -s 'http://127.0.0.1:8000/api/outbox?after=0&limit=20' > linksim/tests/fixtures/outbox_sample.json
while the synthetic L0 session was replayed (readings posted through /api/readings).
If it fails, the hub deviates from D1: raise it with the hub owner, do not edit this test.
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "outbox_sample.json"
KINDS = {"reading", "rep", "alert", "prompt_answer"}
STATUSES = {"ok", "watch", "act", "unknown"}
READING_KEYS = {
    "id", "measured_at", "node", "boot", "seq", "ind", "val", "unit", "src", "q", "crew",
    "status", "rule_id", "source_kind", "escalate_to",
}  # fmt: skip
ALERT_KEYS = {
    "id", "ind", "status", "prev_status", "rule_id", "measured_at", "crew", "escalate_to",
}  # fmt: skip


def test_fixture_shape():
    data = json.loads(FIXTURE.read_text())
    assert set(data) >= {"items", "last_id"}
    items = data["items"]
    assert len(items) >= 5
    assert data["last_id"] == items[-1]["id"]
    ids = [i["id"] for i in items]
    assert all(isinstance(i, int) for i in ids) and ids == sorted(set(ids))
    for it in items:
        assert it["kind"] in KINDS
        assert isinstance(it["created_at"], str) and it["created_at"].endswith("Z")
        assert isinstance(it["payload"], dict)
        if it["kind"] == "reading":
            p = it["payload"]
            assert READING_KEYS <= set(p), READING_KEYS - set(p)
            assert p["status"] in STATUSES
        if it["kind"] == "alert":
            assert ALERT_KEYS <= set(it["payload"])


def test_alert_shape_from_recorded_session():
    """The first 20 outbox items hold no alert, so check the alert in the recorded ground replay."""
    replay = Path(__file__).resolve().parents[2] / "data" / "ground" / "ground-replay.json"
    alerts = [
        i for a in json.loads(replay.read_text())["arrivals"] for i in a["items"]
        if i["kind"] == "alert"
    ]
    assert alerts, "recorded session holds no alert"
    for it in alerts:
        assert ALERT_KEYS <= set(it["payload"])
