"""GET /api/readings with bucket_s.

Without bucket_s the route returns the newest `limit` rows, so a 24-hour or 7-day window at one
reading every 5 s was cut to its last hours. With bucket_s it returns a few stored readings per
time bucket: enough to draw the window from its start and to keep every extreme the lanes judge.
"""

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import MAIN_RULES, Rig, T, reading
from hub.timeutil import parse_iso, to_iso


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


@pytest.fixture
def client(settings, clock, rig):
    s = replace(settings, thresholds_path=MAIN_RULES)
    with TestClient(create_app(s, clock=clock, store=rig.store)) as c:
        yield c


def put_rh(rig, val, at, *, q=("ok",), crew=None):
    """Store one cabin humidity reading measured at `at` (no rule in the test fixture)."""
    rig.seq += 1
    r = reading(ind="cabin_rh", val=val, unit="%", dev="BME280", seq=rig.seq, q=list(q), crew=crew)
    rig.store.insert_reading(r, at)


def get(client, **params):
    r = client.get("/api/readings", params=params)
    assert r.status_code == 200, r.json()
    return r.json()


def test_long_window_keeps_its_start(client, rig):
    for i in range(200):  # 1,000 s at one reading every 5 s
        put_rh(rig, 40 + i % 3, T + timedelta(seconds=5 * i))
    since = to_iso(T)
    raw = get(client, ind="cabin_rh", since=since, limit=50)
    assert raw[0]["measured_at"] == to_iso(T + timedelta(seconds=750))  # the newest 50 only
    rows = get(client, ind="cabin_rh", since=since, limit=50, bucket_s=100)
    assert len(rows) <= 50
    assert rows[0]["measured_at"] == since
    assert rows[-1]["measured_at"] == to_iso(T + timedelta(seconds=995))


def test_bucket_keeps_first_last_lowest_highest(client, rig):
    vals = [42, 43, 79, 41, 42, 17, 42, 42, 43, 44]  # one 60 s bucket, 6 s apart
    for i, v in enumerate(vals):
        put_rh(rig, v, T + timedelta(seconds=6 * i))
    raw = {r["id"]: r for r in get(client, ind="cabin_rh")}
    rows = get(client, ind="cabin_rh", bucket_s=60)
    assert [r["val"] for r in rows] == [42, 79, 17, 44]
    assert all(r == raw[r["id"]] for r in rows)  # stored readings, unchanged
    assert "mean_1h" not in rows[0]  # no mean_1h rule for this indicator


def test_bucket_keeps_flagged_extremes(client, rig):
    put_rh(rig, 42, T)
    for i, v in enumerate((10, 90, 30)):
        put_rh(rig, v, T + timedelta(seconds=10 * (i + 1)), q=("settling",))
    put_rh(rig, 43, T + timedelta(seconds=40))
    rows = get(client, ind="cabin_rh", bucket_s=60)
    assert [(r["val"], r["q"]) for r in rows] == [
        (42, ["ok"]), (10, ["settling"]), (90, ["settling"]), (43, ["ok"]),
    ]  # fmt: skip


def test_bucket_keeps_crew_filter(client, rig):
    put_rh(rig, 41, T, crew="crew-a")
    put_rh(rig, 42, T + timedelta(seconds=5), crew="crew-b")
    rows = get(client, ind="cabin_rh", bucket_s=60, crew="crew-a")
    assert [r["val"] for r in rows] == [41]


def test_bucket_limit_keeps_the_newest(client, rig):
    for i in range(10):
        put_rh(rig, 40 + i, T + timedelta(seconds=60 * i))
    rows = get(client, ind="cabin_rh", bucket_s=60, limit=3)
    assert [r["val"] for r in rows] == [47, 48, 49]


def test_bucket_validation(client):
    def reason(v):
        return client.get(f"/api/readings?ind=cabin_rh&bucket_s={v}").json()["reason"]

    assert reason("abc") == "bad_type:bucket_s"
    assert reason("0") == "bad_value:bucket_s"
    assert reason("86401") == "bad_value:bucket_s"


def _epoch(r):
    return parse_iso(r["measured_at"]).timestamp()


def test_bucket_mean_1h_is_the_assessed_mean(client, rig):
    # The fixture rule t_temp_1h judges cabin_temp on its 1-hour mean, as co2_1h does for CO2.
    for i in range(180):  # 3 hours, one reading a minute
        rig.put("cabin_temp", 22 + (i * 7 % 11) * 0.5 + (3 if 95 <= i < 100 else 0),
                T + timedelta(minutes=i))  # fmt: skip
    since = to_iso(T + timedelta(hours=1))
    raw = get(client, ind="cabin_temp", since=since, limit=5000)
    assessed = {}
    for r in raw:
        (res,) = [a for a in rig.store.results_for(r["id"]) if a.rule_id == "t_temp_1h"]
        assessed[r["id"]] = None if res.status == "unknown" else res.val
    rows = get(client, ind="cabin_temp", since=since, bucket_s=1800)
    assert len(rows) < len(raw)
    for r in rows:
        assert r["mean_1h"] == pytest.approx(assessed[r["id"]])
    # Per bucket, the lowest and highest 1-hour mean survive, so a watch or act mean cannot vanish.
    for b in {int(_epoch(r)) // 1800 for r in raw}:
        want = [assessed[r["id"]] for r in raw if int(_epoch(r)) // 1800 == b]
        got = [r["mean_1h"] for r in rows if int(_epoch(r)) // 1800 == b]
        want = [v for v in want if v is not None]
        got = [v for v in got if v is not None]
        assert (min(got), max(got)) == pytest.approx((min(want), max(want)))


def test_bucket_mean_1h_uses_the_hour_before_since(client, rig):
    for i in range(120):
        rig.put("cabin_temp", 20 + i % 5, T + timedelta(minutes=i))
    since = to_iso(T + timedelta(hours=1))
    rows = get(client, ind="cabin_temp", since=since, bucket_s=600)
    assert rows[0]["measured_at"] == since and rows[0]["mean_1h"] is not None
