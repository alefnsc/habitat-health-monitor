from datetime import timedelta

import pytest

from hub.signals import methods as M
from hub.tests.signals.kit import END, lift_set, one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_work_falls_across_the_latest_set(rig):
    lift_set(rig, "s-0", END - timedelta(days=1), [16.0, 16.9, 17.5, 18.2, 19.0, 19.5, 20.0])
    lift_set(rig, "s-1", END - timedelta(hours=2), [20.0, 19.5, 19.0, 18.2, 17.5, 16.9, 16.0])
    s = one(rig, "lift_within_set")
    assert s.state == "notable" and s.headline_key == "signals.trend.down"
    assert s.value.unit == "kg_m" and s.value.per == "rep" and s.detail["exercise"] == "curl"
    assert s.detail["session"] == "s-1"  # the latest set, not the rising one before it
    assert len(s.inputs) == 1 and s.inputs[0].n == 7 and s.inputs[0].src == "camera"


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


def test_work_across_sets_divides_by_g(rig):
    for k in range(10):
        g = 9.81 if k % 2 == 0 else 1.62  # Earth and Moon sets of the same exercise
        lift_set(rig, f"c-{k}", END - timedelta(days=20 - 2 * k), [(18.0 + 0.4 * k) * g] * 6, g=g)
    s = one(rig, "lift_work_sets")
    assert [v for _, v in s.series] == pytest.approx([18.0 + 0.4 * k for k in range(10)])
    assert s.headline_key == "signals.trend.up" and s.inputs[0].n == 60


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


TILT = {"node": "tilt-1", "dev": "KY017", "src": "hobby"}


def tilt_set(rig, sid, start, offset_ms, reps=3, witnessed=None):
    """A camera set whose tilt switch rises and falls around each rep's turnaround, centred
    `offset_ms` after it. Reps past `witnessed` carry a turnaround but no tilt change."""
    witnessed = reps if witnessed is None else witnessed
    put_ref(rig, "tilt", 0, start, **TILT)  # at rest before the set
    for i in range(1, witnessed + 1):
        turn = start + timedelta(seconds=5 * i, milliseconds=-750)  # rep i ends at start + 5 i s
        put_ref(rig, "tilt", 1, turn + timedelta(milliseconds=offset_ms - 100), **TILT)
        put_ref(rig, "tilt", 0, turn + timedelta(milliseconds=offset_ms + 100), **TILT)
    lift_set(rig, sid, start, [20.0] * reps, turn_ms=750)


USUAL = [20, 30, 25, 35, 28, 22, 32, 27, 33]


def _tilt_sets(rig, offsets, witnessed_last=None):
    for k, off in enumerate(offsets):
        last = k == len(offsets) - 1
        tilt_set(rig, f"t-{k}", END - timedelta(days=40 - k), off,
                 witnessed=witnessed_last if last else None)  # fmt: skip


def test_tilt_one_late_set_is_above_the_usual_range_but_steady(rig):
    _tilt_sets(rig, [*USUAL, 200], witnessed_last=2)
    s = one(rig, "lift_tilt_agreement")
    assert s.headline_key == "signals.baseline.above" and s.state == "steady"
    b = M.own_baseline(USUAL, min_n=7)
    assert (s.value.estimate, s.value.low, s.value.high) == pytest.approx((200, b.low, b.high))
    assert s.method.n == 9 and s.detail["tilt_share"] == pytest.approx(2 / 3)


def test_tilt_two_late_sets_in_a_row_are_notable(rig):
    _tilt_sets(rig, [*USUAL, 200, 210])
    s = one(rig, "lift_tilt_agreement")
    assert s.headline_key == "signals.baseline.above" and s.state == "notable"
    assert s.detail["tilt_share"] == 1.0


def test_tilt_inside_the_usual_range(rig):
    _tilt_sets(rig, [*USUAL, 29])
    s = one(rig, "lift_tilt_agreement")
    assert s.headline_key == "signals.baseline.inside" and s.state == "steady"


def test_tilt_range_uses_only_the_last_14_prior_sets(rig):
    old = [100, 110, 120, 130]
    usual = [*USUAL, 24, 31, 26, 29, 23]  # 14 sets
    _tilt_sets(rig, [*old, *usual, 60])
    s = one(rig, "lift_tilt_agreement")
    b14, ball = M.own_baseline(usual, min_n=7), M.own_baseline([*old, *usual], min_n=7)
    assert (b14.low, b14.high) != pytest.approx((ball.low, ball.high))
    assert (s.value.low, s.value.high) == pytest.approx((b14.low, b14.high))
    assert s.method.n == 18  # every earlier witnessed set is counted; the range takes 14
