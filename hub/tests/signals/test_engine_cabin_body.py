from datetime import timedelta
from pathlib import Path

import pytest

from hub.signals.engine import evaluate
from hub.tests.helpers import Rig, T

TZ = "America/Sao_Paulo"
REAL_RULES = Path(__file__).resolve().parents[3] / "data" / "thresholds.json"


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock, rule_files=(REAL_RULES,))


def one(rig, sid, crews=("crew-a",), at=T):
    [s] = [x for x in evaluate(rig.store, rig.assessor.rules, crews=list(crews), at=at, tz=TZ,
                               ids=[sid])]  # fmt: skip
    return s


def fill_cabin(rig, ind, f, minutes, step_s=60, end=T):
    n = minutes * 60 // step_s
    for i in range(n):
        at = end - timedelta(seconds=step_s * (n - 1 - i))
        rig.put(ind, f(i * step_s / 3600), at)


def test_cabin_trend_rising_is_notable(rig):
    fill_cabin(rig, "cabin_temp", lambda h: 21 + 0.5 * h, 6 * 60)
    s = one(rig, "cabin_temp_6h")
    assert s.state == "notable" and s.headline_key == "signals.trend.up"
    assert s.value.low > 0 and s.value.estimate == pytest.approx(0.5, abs=0.05)
    assert s.value.unit == "C" and s.value.per == "h" and s.crew is None and not s.replay


def test_cabin_trend_flat_is_steady(rig):
    fill_cabin(rig, "cabin_temp", lambda h: 22.0, 6 * 60)
    s = one(rig, "cabin_temp_6h")
    assert s.state == "steady" and s.headline_key == "signals.trend.flat"


def test_cabin_trend_gap_is_not_enough_data(rig):
    fill_cabin(rig, "cabin_temp", lambda h: 21 + h, 2 * 60)  # only the last 2 of 6 hours
    s = one(rig, "cabin_temp_6h")
    assert s.state == "not_enough_data" and s.value is None
    assert s.missing[0].key == "signals.missing.blocks" and s.missing[0].need == 27
    assert s.missing[0].have == 12


def test_rh_heading_for_75_reaches_in_hours(rig):
    fill_cabin(
        rig, "cabin_rh", lambda h: 60 + 4 * h, 2 * 60
    )  # current = median of the last 3 blocks, about 67.4 %: (75 - 67.4) / 4 = 1.9 h
    s = one(rig, "cabin_rh_ttl")
    assert s.headline_key == "signals.ttl.reaches" and s.state == "notable"
    assert s.reference["limit"] == 75 and s.value.unit == "h"
    assert s.value.low == pytest.approx(1.9, abs=0.05) and s.value.high >= s.value.low


def test_rh_falling_away_from_75_heads_for_25_not_shown(rig):
    fill_cabin(rig, "cabin_rh", lambda h: 60 - 1 * h, 2 * 60)  # 58 % falling 1 %/h: 33 h to 25 %
    s = one(rig, "cabin_rh_ttl")
    assert s.state == "steady" and s.headline_key == "signals.ttl.none" and s.value is None


def put_night(rig, day_end, sleep_h, hr, crew="crew-a"):
    for k in range(int(sleep_h * 12)):
        at = day_end - timedelta(minutes=5 * k + 2)
        rig.put("hr", hr, at, node="ring-1", dev="RING", crew=crew)
    rig.put("sleep_h", sleep_h, day_end, node="ring-1", dev="RING", crew=crew)


def test_rest_hr_one_night_above_own_range_is_shown_not_notable(rig):
    end = T.replace(hour=10)  # 07:00 local
    for d in range(16, 0, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 56 + (d % 3))  # 56-58 usual
    put_night(rig, end, 7.0, 66)
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert s.headline_key == "signals.baseline.above" and s.state == "steady"
    assert s.value.estimate == 66 and s.value.low < 57 < s.value.high


def test_rest_hr_two_nights_above_own_range_is_notable(rig):
    end = T.replace(hour=10)
    for d in range(17, 1, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 56 + (d % 3))
    put_night(rig, end - timedelta(days=1), 7.0, 65)
    put_night(rig, end, 7.0, 66)
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert s.state == "notable" and s.can_trigger


def test_rest_hr_ignores_replay_when_real_nights_exist(rig):
    end = T.replace(hour=10)
    for d in range(10, -1, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 57 + d % 2)
    rig.put(
        "sleep_h",
        8.0,
        end - timedelta(hours=1),
        node="sim-1",
        dev="RING",
        src="replay",
        crew="crew-a",
    )
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert not s.replay and all(i.src != "replay" for i in s.inputs)


def test_rest_hr_baseline_needs_7_prior_nights(rig):
    end = T.replace(hour=10)
    for d in range(4, -1, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 57 + d % 2)
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert s.state == "not_enough_data" and s.missing[0].key == "signals.missing.priorDays"
    assert (s.missing[0].need, s.missing[0].have) == (7, 4)


def test_body_signals_are_per_crew_and_cabin_once(rig):
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a", "crew-c"], at=T, tz=TZ)
    ids = [(s.id, s.crew) for s in out]
    assert ("cabin_temp_6h", None) in ids and ("rest_hr_baseline", "crew-a") in ids
    assert ("rest_hr_baseline", "crew-c") in ids
    assert sum(1 for i, _ in ids if i == "cabin_temp_6h") == 1


def test_a_late_ring_sync_changes_the_signal_on_the_next_read(rig):
    end = T.replace(hour=10)
    for d in range(10, 0, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 56 + d % 3)  # usual 56-58
    at = end + timedelta(hours=9)  # 16:00 local: last night has not synced yet
    before = one(rig, "rest_hr_baseline", at=at)
    # The sync lands 9 hours late; age_ms puts measured_at back on the true night.
    rig.clock.set(at)
    for k in range(84):
        t = end - timedelta(minutes=5 * k + 2)
        rig.put("hr", 66, at, node="ring-1", dev="RING", crew="crew-a",
                age_ms=int((at - t).total_seconds() * 1000))  # fmt: skip
    rig.put("sleep_h", 7.0, at, node="ring-1", dev="RING", crew="crew-a",
            age_ms=int((at - end).total_seconds() * 1000))  # fmt: skip
    after = one(rig, "rest_hr_baseline", at=at)
    assert before.value.estimate != after.value.estimate
    assert after.value.estimate == 66 and after.headline_key == "signals.baseline.above"
