"""Contract check of the hub outbox (resolution D1, alert shape D3) against a recorded sample.

The fixture is recorded from the real hub once GET /api/outbox (H12) exists:
  curl -s 'http://127.0.0.1:8000/api/outbox?after=0&limit=20' > linksim/tests/fixtures/outbox_sample.json
while sim-1 replays data/replay/l0-synthetic.jsonl. Until then this test is skipped.
If it fails, the hub deviates from D1: raise it with the hub owner, do not edit this test.
"""

import json
from pathlib import Path

import pytest

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


@pytest.mark.skipif(not FIXTURE.exists(), reason="outbox_sample.json not recorded yet (needs H12)")
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
