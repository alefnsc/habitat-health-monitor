import json
import subprocess
import sys
from pathlib import Path

from receiver.export import export_replay
from receiver.store import ingest, open_db

BEACON = {
    "link": {"state": "contact", "light_time_s": 900, "time_scale": 30, "queue_len": 0,
             "last_blackout": None},
    "hold_s": 30.0, "in_flight": 0, "fetched_id": 1, "delivered_id": 1,
    "last_blackout_cause": None, "sent_at": "2026-11-15T13:00:00.000Z",
}
GROUND = Path(__file__).resolve().parents[2]


def _item(i):
    return {"id": i, "kind": "reading", "created_at": "z", "payload": {"n": i}}


def _db(tmp_path, beacon=BEACON):
    conn = open_db(tmp_path / "g.db")
    ingest(conn, beacon, [_item(1)], "2026-11-15T13:00:00.000Z")
    ingest(conn, None, [_item(2)], "2026-11-15T13:00:05.000Z")
    ingest(conn, None, [_item(3)], "2026-11-15T13:10:00.000Z")
    return conn


def test_window(tmp_path):
    r = export_replay(_db(tmp_path), "2026-11-15T13:00:00Z", "2026-11-15T13:05:00Z", "x")
    assert [a["at_ms"] for a in r["arrivals"]] == [0, 5000]
    assert r["t0"] == "2026-11-15T13:00:00.000Z"


def test_header(tmp_path):
    r = export_replay(_db(tmp_path), None, None, "lbl")
    assert r["v"] == 1 and r["kind"] == "ground-replay" and r["label"] == "lbl"
    assert (r["light_time_s"], r["time_scale"]) == (900, 30)
    assert r["exported_at"].endswith("Z")
    assert len(r["arrivals"]) == 3


def test_no_beacon(tmp_path):
    r = export_replay(_db(tmp_path, beacon=None), None, None, "lbl")
    assert (r["light_time_s"], r["time_scale"]) == (720, 60)
    assert r["label"] == "lbl (link parameters assumed)"


def _cli(db, out, *extra):
    return subprocess.run(
        [sys.executable, "-m", "receiver.export", "--db", str(db), "--out", str(out),
         "--label", "L", *extra],
        cwd=GROUND, capture_output=True, text=True, check=False,
    )


def test_empty_window(tmp_path):
    _db(tmp_path)
    out = tmp_path / "o.json"
    p = _cli(tmp_path / "g.db", out, "--since", "2030-01-01T00:00:00Z")
    assert p.returncode == 1 and "no arrivals in window" in p.stdout + p.stderr
    assert not out.exists()


def test_cli_writes(tmp_path):
    _db(tmp_path)
    out = tmp_path / "o.json"
    p = _cli(tmp_path / "g.db", out)
    assert p.returncode == 0, p.stderr
    data = json.loads(out.read_text())
    ids = [i["id"] for a in data["arrivals"] for i in a["items"]]
    assert len(data["arrivals"]) == 3 and ids == [1, 2, 3]
    assert "MB" in p.stdout
