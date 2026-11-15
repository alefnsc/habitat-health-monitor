import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hub.contract import parse_reading
from nodes.weather.__main__ import run_pull
from nodes.weather.location import LocationError, coarse_location, env_file_values
from nodes.weather.mapper import HourRow, map_hours
from nodes.weather.provider import NoProvider

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[3]


def rows(n=3):
    return [HourRow(NOW - timedelta(hours=n - i), 20.0 + i, 60.0, 1012.0) for i in range(n)]


def test_hours_map_to_valid_contract_readings():
    out = map_hours(rows(), now_ms=int(NOW.timestamp() * 1000))
    assert len(out) == 9 and [r["ind"] for r in out[:3]] == ["earth_temp", "earth_rh", "earth_p"]
    for r in out:
        parse_reading(r)  # the hub's own contract accepts it
        assert (r["node"], r["src"], r["dev"]) == ("earth-1", "ref", "WEATHER")
        assert "crew" not in r and "lat" not in r and "lon" not in r
    assert out[0]["age_ms"] == 3 * 3_600_000


def test_missing_values_stay_missing_and_forecasts_are_dropped():
    rs = [HourRow(NOW - timedelta(hours=1), None, 55.0, None),
          HourRow(NOW + timedelta(hours=1), 25.0, 50.0, 1010.0)]  # fmt: skip
    out = map_hours(rs, now_ms=int(NOW.timestamp() * 1000))
    assert [r["ind"] for r in out] == ["earth_rh"]


def test_out_of_range_is_flagged_not_dropped():
    [r] = map_hours([HourRow(NOW, None, 120.0, None)], now_ms=int(NOW.timestamp() * 1000))
    assert r["q"] == ["out_of_range"]


def test_seq_is_fixed_per_hour_so_a_second_pull_is_a_duplicate():
    a = map_hours(rows(), now_ms=int(NOW.timestamp() * 1000))
    b = map_hours(rows(), now_ms=int((NOW + timedelta(minutes=5)).timestamp() * 1000))
    assert [r["seq"] for r in a] == [r["seq"] for r in b]


def test_location_is_coarse_and_env_wins():
    # invented coordinates, not anyone's location
    assert coarse_location({"WEATHER_LAT": "12.3456", "WEATHER_LON": "-45.6789"}, {}) == (
        12.3,
        -45.7,
    )
    assert coarse_location({}, {"WEATHER_LAT": "10.04", "WEATHER_LON": "20.06"}) == (10.0, 20.1)
    with pytest.raises(LocationError):
        coarse_location({}, {})
    with pytest.raises(LocationError):
        coarse_location({"WEATHER_LAT": "95", "WEATHER_LON": "0"}, {})


def test_run_pull_counts_and_dry_run_posts_nothing():
    class Fake:
        def hours(self, start, end):
            return rows()

    posted = []
    c = run_pull(Fake(), hours=3, now=NOW, post=lambda rs: posted.extend(rs) or {"stored": len(rs)})
    assert c == {"hours": 3, "readings": 9, "stored": 9} and len(posted) == 9
    assert run_pull(Fake(), hours=3, now=NOW, post=None) == {"hours": 3, "readings": 9}


def test_no_provider_refuses():
    with pytest.raises(RuntimeError, match="no weather provider"):
        NoProvider().hours(NOW, NOW)


def test_the_bench_location_is_in_no_tracked_file():
    env = env_file_values(REPO / ".env")
    raw = [env[k] for k in ("WEATHER_LAT", "WEATHER_LON") if env.get(k)]
    if len(raw) < 2:
        pytest.skip("no local .env location to check")
    lat, lon = coarse_location({}, env)
    coarse = (f"{lat:.1f}", f"{lon:.1f}")
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()  # fmt: skip
    leaks = []
    for f in tracked:
        p = REPO / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        # the exact values, or the coarse cell (both coordinates in one file)
        if any(v in text for v in raw) or all(c in text for c in coarse):
            leaks.append(f)
    # the message names the files only, never the location
    assert not leaks, f"tracked files hold the bench location: {leaks}"
