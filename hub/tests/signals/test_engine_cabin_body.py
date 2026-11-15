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


# Review follow-ups (2026-11-15): night-window rules, sources, the 14-night cap and the untested signals.


def test_a_manual_sleep_entry_does_not_replace_the_ring_night(rig):
    end = T.replace(hour=10)
    for d in range(10, -1, -1):
        put_night(rig, end - timedelta(days=d), 7.0 + 0.1 * (d % 3), 57)
    # a self-reported sleep_h later the same morning: not the ring's night
    rig.put("sleep_h", 4.0, end + timedelta(hours=2), node="manual", dev="manual", src="self",
            crew="crew-a")  # fmt: skip
    s = one(rig, "sleep_baseline", at=end + timedelta(hours=3))
    assert s.value.estimate == pytest.approx(7.0) and all(i.dev == "RING" for i in s.inputs)


def test_hr_outside_the_night_window_is_ignored(rig):
    from zoneinfo import ZoneInfo

    from hub.signals import inputs as I

    end = T.replace(hour=10)
    put_night(rig, end, 7.0, 57)
    for k in range(1, 13):  # awake samples after the wake time
        rig.put("hr", 95, end + timedelta(minutes=5 * k), node="ring-1", dev="RING", crew="crew-a")
    [night], replay = I.nights(rig.store, "crew-a", end + timedelta(hours=2), 2, ZoneInfo(TZ))
    value, rows = I.night_rest_hr(rig.store, "crew-a", night, replay)
    assert value == 57
    # the awake rows are not in the night at all (a median alone could hide a few of them)
    assert rows and all(I.parse_iso(r.measured_at) <= night.end for r in rows)
    assert all(r.val == 57 for r in rows)


def test_a_night_under_half_covered_by_hr_has_no_resting_hr(rig):
    from zoneinfo import ZoneInfo

    from hub.signals import inputs as I

    end = T.replace(hour=10)
    for k in range(0, 84, 3):  # one block in three: about 33 % of the night
        rig.put(
            "hr", 57, end - timedelta(minutes=5 * k + 2), node="ring-1", dev="RING", crew="crew-a"
        )
    rig.put("sleep_h", 7.0, end, node="ring-1", dev="RING", crew="crew-a")
    [night], replay = I.nights(rig.store, "crew-a", end + timedelta(hours=1), 2, ZoneInfo(TZ))
    assert I.night_rest_hr(rig.store, "crew-a", night, replay)[0] is None


def test_hr_without_a_sleep_h_reading_makes_no_night(rig):
    end = T.replace(hour=10)
    for k in range(84):
        rig.put(
            "hr", 57, end - timedelta(minutes=5 * k + 2), node="ring-1", dev="RING", crew="crew-a"
        )
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert s.state == "not_enough_data" and s.missing[0].key == "signals.missing.recentNight"


def test_replay_hr_is_not_pooled_into_real_nights(rig):
    end = T.replace(hour=10)
    for d in range(10, -1, -1):
        t = end - timedelta(days=d)
        rig.put("sleep_h", 7.0, t, node="ring-1", dev="RING", crew="crew-a")
        for k in range(84):  # only replay HR inside the real nights
            rig.put("hr", 57 + d % 3, t - timedelta(minutes=5 * k + 2), node="sim-1", dev="RING",
                    src="replay", crew="crew-a")  # fmt: skip
    s = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert not s.replay and s.state == "not_enough_data"
    assert all(i.src != "replay" for i in s.inputs)


def put_spo2(rig, val, at):
    """Rig.put has no default device for spo2: build the ring reading here."""
    rig.clock.set(at)
    rig.seq += 1
    m = {"v": 1, "node": "ring-1", "boot": 1, "seq": rig.seq, "age_ms": 0, "ind": "spo2", "val": val,
         "unit": "%", "src": "hobby", "dev": "RING", "q": ["ok"], "crew": "crew-a"}  # fmt: skip
    assert rig.ing.ingest_reading(m, channel="test").reason is None


def test_spo2_counts_only_below_the_range_as_notable(rig):
    end = T.replace(hour=10)
    for d in range(17, 1, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 57)
        put_spo2(rig, 96.0 + 0.5 * (d % 3), end - timedelta(days=d))
    for d in (1, 0):
        put_night(rig, end - timedelta(days=d), 7.0, 57)
        put_spo2(rig, 99.8, end - timedelta(days=d))
    high = one(rig, "spo2_baseline", at=end + timedelta(hours=1))
    assert high.headline_key == "signals.baseline.above" and high.state == "steady"
    for d in (1, 0):
        put_spo2(rig, 93.0, end - timedelta(days=d) + timedelta(minutes=1))
    low = one(rig, "spo2_baseline", at=end + timedelta(hours=1))
    assert low.headline_key == "signals.baseline.below" and low.state == "notable"


def test_rest_hr_14n_fits_at_most_14_nights_and_finds_a_rise(rig):
    end = T.replace(hour=10)
    for d in range(16, -1, -1):
        # wake 30 minutes later on the oldest day, so 15 local dates fall in the 14-day window
        late = timedelta(minutes=30) if d == 14 else timedelta(0)
        put_night(rig, end - timedelta(days=d) + late, 7.0, 70 - d)
    s = one(rig, "rest_hr_14n", at=end + timedelta(minutes=10))
    assert s.method.n == 14 and s.method.coverage <= 1
    assert s.state == "notable" and s.headline_key == "signals.trend.up" and s.value.per == "day"


def test_cabin_temp_heading_for_27_reaches_in_about_an_hour(rig):
    fill_cabin(rig, "cabin_temp", lambda h: 24.0 + 1.0 * h, 2 * 60)
    s = one(rig, "cabin_temp_ttl")
    assert s.headline_key == "signals.ttl.reaches" and s.reference["limit"] == 27
    assert s.state == "notable" and s.value.low == pytest.approx(1.1, abs=0.1)


def test_cabin_ppco2_ttl_fits_the_trailing_1h_mean(rig):
    from hub.derive import ppco2_mmhg

    for i in range(3 * 60):  # 3 hours, one CO2 sample a minute, pressure a second before each
        at = T - timedelta(minutes=3 * 60 - 1 - i)
        rig.put("cabin_p", 1013.0, at - timedelta(seconds=1))
        rig.put("cabin_co2", 1500.0 + 1000.0 * i / 60, at)
    s = one(rig, "cabin_ppco2_ttl")
    last_mean = s.series[-1][1]
    raw_now = ppco2_mmhg(1500.0 + 1000.0 * (3 * 60 - 1) / 60, 1013.0)
    mean_now = ppco2_mmhg(1500.0 + 1000.0 * (3 * 60 - 1 - 30) / 60, 1013.0)  # mean lags ~30 min
    assert last_mean == pytest.approx(mean_now, abs=0.05) and last_mean < raw_now - 0.2


def test_non_ring_spo2_and_hr_never_enter_a_night(rig):
    end = T.replace(hour=10)
    for d in range(10, -1, -1):
        put_night(rig, end - timedelta(days=d), 7.0, 56 + d % 3)
        put_spo2(rig, 96.0 + 0.5 * (d % 3), end - timedelta(days=d))
    # a finger-clip reading of the same crew, the same night: not the ring
    rig.clock.set(end - timedelta(minutes=1))
    rig.seq += 1
    clip = {"v": 1, "node": "vitals-1", "boot": 1, "seq": rig.seq, "age_ms": 0, "ind": "spo2",
            "val": 90.0, "unit": "%", "src": "hobby", "dev": "MAX30102", "q": ["ok"], "crew": "crew-a"}  # fmt: skip
    assert rig.ing.ingest_reading(clip, channel="test").reason is None
    for k in range(84):  # a strap HR at 95 inside the ring night
        rig.put("hr", 95, end - timedelta(minutes=5 * k + 1), node="vitals-1", dev="MAX30102",
                crew="crew-a")  # fmt: skip
    spo2 = one(rig, "spo2_baseline", at=end + timedelta(hours=1))
    assert spo2.value.estimate != 90.0 and all(i.dev == "RING" for i in spo2.inputs)
    hr = one(rig, "rest_hr_baseline", at=end + timedelta(hours=1))
    assert hr.value.estimate < 60 and all(i.dev == "RING" for i in hr.inputs)
