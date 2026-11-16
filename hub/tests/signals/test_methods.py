"""hub/signals/methods.py against hand-worked values (D45 §6, §10).

The values below are worked from the formulas by hand:
- strictly rising 1..10: S = 45, Var(S) = 10*9*25/18 = 125, Z = (45 - 1)/sqrt(125) = 3.9355;
- the tied series has two pairs of ties: Var(S) = (2250 - 2*18)/18 = 123.
"""

from datetime import date, timedelta

import pytest

from hub.signals import methods as M


def test_mann_kendall_strictly_rising():
    mk = M.mann_kendall(list(range(1, 11)))
    assert (mk.n, mk.s, mk.var_s) == (10, 45, 125.0)
    assert mk.z == pytest.approx(3.93548, abs=1e-5)
    assert mk.p == pytest.approx(8.303e-05, rel=1e-3)


def test_mann_kendall_tie_correction():
    mk = M.mann_kendall([1, 2, 2, 3, 5, 4, 6, 6, 7, 9])
    assert (mk.s, mk.var_s) == (41, 123.0)
    assert mk.z == pytest.approx(3.60668, abs=1e-5)


def test_mann_kendall_all_ties_is_no_trend():
    mk = M.mann_kendall([5.0] * 12)
    assert (mk.s, mk.var_s, mk.z, mk.p) == (0, 0.0, 0.0, 1.0)


def test_mann_kendall_needs_three_points():
    assert M.mann_kendall([1, 2]) is None


def test_sen_slope_and_interval():
    xs = [1, 2, 2, 3, 5, 4, 6, 6, 7, 9]
    mk = M.mann_kendall(xs)
    sen = M.sen_slope(list(enumerate(xs)), mk.var_s)
    assert sen.n_slopes == 45 and sen.slope == pytest.approx(0.8)
    assert sen.low == pytest.approx(0.56315, abs=1e-5) and sen.high == pytest.approx(1.0)


def test_sen_slope_skips_equal_times():
    assert M.sen_slope([(0, 1.0), (0, 2.0)], 1.0) is None


def test_at_rank_interpolates_and_clamps():
    assert M._at_rank([1, 2, 3, 4], 2.5) == 2.5
    assert M._at_rank([1, 2, 3, 4], 0) == 1 and M._at_rank([1, 2, 3, 4], 9) == 4


def test_trend_notable_needs_p_and_interval_off_zero():
    rising = M.trend(list(enumerate([1, 2, 2, 3, 5, 4, 6, 6, 7, 9])), min_n=10)
    assert rising.notable and rising.low > 0
    noisy = M.trend(list(enumerate([3, 1, 4, 1, 5, 9, 2, 6, 5, 3])), min_n=10)
    assert not noisy.notable and noisy.low < 0 < noisy.high
    flat = M.trend([(i, 5.0) for i in range(12)], min_n=10)
    assert not flat.notable and (flat.slope, flat.low, flat.high) == (0.0, 0.0, 0.0)


def test_trend_below_min_n_is_none():
    assert M.trend([(i, float(i)) for i in range(9)], min_n=10) is None


def test_own_baseline_range():
    b = M.own_baseline([60, 62, 61, 63, 59, 60, 64])
    # median 61, MAD 1: 61 +/- 2 * 1.4826
    assert (b.median, b.mad, b.n) == (61, 1, 7)
    assert b.low == pytest.approx(58.0348) and b.high == pytest.approx(63.9652)


def test_own_baseline_needs_7_and_spread():
    assert M.own_baseline([60, 61, 62, 63, 64, 65]) is None
    assert M.own_baseline([60] * 7) is None


def test_outside_sides():
    b = M.Baseline(61, 1, 58, 64, 7)
    assert M.outside(65, b) and M.outside(57, b) and not M.outside(60, b)
    assert not M.outside(65, b, "low") and M.outside(57, b, "low")
    assert M.outside(65, b, "high") and not M.outside(57, b, "high")


def test_time_to_limit():
    assert M.time_to_limit(70, 1.0, 2.0, 75) == (2.5, 5.0)  # rising toward 75
    assert M.time_to_limit(30, -2.0, -1.0, 25) == (2.5, 5.0)  # falling toward 25
    assert M.time_to_limit(70, -2.0, -1.0, 75) is None  # heading away
    assert M.time_to_limit(70, -1.0, 1.0, 75) is None  # interval includes 0
    assert M.time_to_limit(70, 0.2, 0.5, 75) is None  # far end 25 h > 12 h


def test_spearman_and_interval():
    pairs = [(i, i * 2 + (i % 3)) for i in range(20)]
    s = M.spearman(pairs)
    assert s.n == 20 and s.rho == pytest.approx(0.99774, abs=1e-5)
    assert s.low < s.rho < s.high <= 1
    weak = M.spearman([(i, (-1) ** i) for i in range(20)])
    assert weak.low < 0 < weak.high


def test_spearman_perfect_order_interval_contains_rho():
    s = M.spearman([(i, -i) for i in range(20)])
    assert s.rho == pytest.approx(-1.0) and s.low <= s.rho <= s.high


def test_spearman_needs_20_pairs_and_spread():
    assert M.spearman([(i, i) for i in range(19)]) is None
    assert M.spearman([(i, 1.0) for i in range(25)]) is None


def test_lagged_pairs_drop_a_missing_side():
    d = date(2026, 11, 1)
    xs = {d: 1.0, d + timedelta(days=1): 2.0}
    ys = {d + timedelta(days=1): 10.0, d + timedelta(days=3): 30.0}
    assert M.lagged_pairs(xs, ys, lag=timedelta(days=1)) == [(d, 1.0, 10.0)]
