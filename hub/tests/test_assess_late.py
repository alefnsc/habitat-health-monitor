"""Hours-old readings (a delayed cloud sync, D41 §6): assessed at their measured time, never "now"."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from hub.api import create_app

ROOT = Path(__file__).resolve().parents[2]
SIX_H_MS = 6 * 3600 * 1000
HR = {"v": 1, "node": "ring-1", "boot": 1, "seq": 41, "age_ms": SIX_H_MS, "ind": "hr", "val": 140,
      "unit": "bpm", "src": "hobby", "dev": "RING", "q": ["ok"], "crew": "crew-b"}  # fmt: skip


def test_six_hour_old_reading_is_assessed_and_alerted_at_its_measured_time(settings, clock):
    s = replace(settings, thresholds_path=ROOT / "data" / "thresholds.json")
    with TestClient(create_app(s, clock=clock)) as c:
        r = c.post("/api/readings", json=HR)
        assert r.status_code == 201
        body = r.json()
        # FakeClock is 2026-11-14 12:00Z, so the reading was measured at 06:00Z
        assert body["measured_at"] == "2026-11-14T06:00:00.000Z"
        assert {e["rule_id"]: e["status"] for e in body["results"]}["hr_rest_high"] == "act"
        items = c.get("/api/outbox").json()["items"]
        alerts = [i["payload"] for i in items if i["kind"] == "alert"]
        assert alerts and all(a["measured_at"] == "2026-11-14T06:00:00.000Z" for a in alerts)
        assert all(a["crew"] == "crew-b" for a in alerts)
        # no command of any kind is queued by a body alert (the buzzer is space-weather only)
        assert not [i for i in items if i["kind"] in ("cmd", "command")]
