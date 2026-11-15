from datetime import timedelta

import pytest

from hub.tests.signals.kit import END, lift_set, one, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_work_falls_across_the_latest_set(rig):
    lift_set(rig, "s-1", END - timedelta(hours=2), [20.0, 19.5, 19.0, 18.2, 17.5, 16.9, 16.0])
    s = one(rig, "lift_within_set")
    assert s.state == "notable" and s.headline_key == "signals.trend.down"
    assert s.value.unit == "kg_m" and s.value.per == "rep" and s.detail["exercise"] == "curl"


def test_within_set_needs_6_reps(rig):
    lift_set(rig, "s-1", END - timedelta(hours=2), [20.0, 19.0, 18.0])
    s = one(rig, "lift_within_set")
    assert s.state == "not_enough_data" and s.missing[0].key == "signals.missing.reps"


def test_work_across_sets_one_exercise(rig):
    for k in range(10):
        lift_set(rig, f"c-{k}", END - timedelta(days=20 - 2 * k), [18.0 + 0.4 * k] * 6)
    lift_set(rig, "r-1", END - timedelta(days=30), [40.0] * 6, exercise="row")
    s = one(rig, "lift_work_sets")
    assert s.state == "notable" and s.headline_key == "signals.trend.up"
    assert s.method.n == 10 and s.detail["exercise"] == "curl"


def test_replay_sets_are_not_mixed_with_real_sets(rig):
    for k in range(10):
        lift_set(rig, f"c-{k}", END - timedelta(days=20 - 2 * k), [18.0] * 6)
    lift_set(rig, "sim", END - timedelta(days=1), [99.0] * 6, node="sim-1")
    s = one(rig, "lift_work_sets")
    assert not s.replay and s.method.n == 10


def test_tilt_agreement_without_tilt_readings_is_not_enough_data(rig):
    lift_set(rig, "s-1", END - timedelta(hours=2), [20.0] * 6)
    s = one(rig, "lift_tilt_agreement")
    assert s.state == "not_enough_data"  # the reps carry no turnaround, so no witness
