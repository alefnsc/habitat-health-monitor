"""Signal statistics (D45 §6). Pure, standard library only: no store, no clock, no I/O.

Every function returns None when it cannot give an honest answer, and the engine turns that into
`not_enough_data`. Nothing here fills a gap: callers pass only the points that exist.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from statistics import NormalDist

ALPHA = 0.05
MAD_SCALE = 1.4826  # MAD -> standard deviation for normal data
_N = NormalDist()

MK_REF = "Mann (1945); Kendall (1975); Gilbert (1987) ch. 16"
SEN_REF = "Sen (1968); confidence interval by Gilbert (1987) 16.5"
BASELINE_REF = "median and MAD (scaled by 1.4826) of the previous days"
TTL_REF = "Sen slope interval of the last 2 h, extended to the limit"
SPEARMAN_REF = (
    "Spearman rank correlation; Fisher-z interval, SE 1.03/sqrt(n-3) (Fieller et al. 1957)"
)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


@dataclass(frozen=True)
class MannKendall:
    n: int
    s: int
    var_s: float
    z: float
    p: float


def mann_kendall(xs: Sequence[float]) -> MannKendall | None:
    """Two-sided Mann-Kendall test with the tie-corrected variance. Needs n >= 3."""
    n = len(xs)
    if n < 3:
        return None
    s = sum(_sign(xs[j] - xs[i]) for i in range(n - 1) for j in range(i + 1, n))
    ties = sum(t * (t - 1) * (2 * t + 5) for t in Counter(xs).values() if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - ties) / 18
    if var_s <= 0:
        return MannKendall(n, s, 0.0, 0.0, 1.0)
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2 * (1 - _N.cdf(abs(z)))
    return MannKendall(n, s, var_s, z, p)


def _at_rank(sorted_vals: Sequence[float], rank: float) -> float:
    """Value at a 1-based, possibly fractional rank, linearly interpolated and clamped."""
    r = min(max(rank, 1.0), float(len(sorted_vals)))
    lo = math.floor(r)
    hi = math.ceil(r)
    if lo == hi:
        return sorted_vals[lo - 1]
    frac = r - lo
    return sorted_vals[lo - 1] * (1 - frac) + sorted_vals[hi - 1] * frac


@dataclass(frozen=True)
class SenSlope:
    slope: float
    low: float
    high: float
    n_slopes: int


def sen_slope(
    points: Sequence[tuple[float, float]], var_s: float, alpha: float = ALPHA
) -> SenSlope | None:
    """Median of pairwise slopes (dx/dt) and its rank-based interval. `points` are (t, x),
    t ascending; pairs with equal t are skipped. `var_s` is Mann-Kendall's tie-corrected variance."""
    slopes = sorted(
        (points[j][1] - points[i][1]) / (points[j][0] - points[i][0])
        for i in range(len(points) - 1)
        for j in range(i + 1, len(points))
        if points[j][0] != points[i][0]
    )
    if not slopes:
        return None
    n = len(slopes)
    c = _N.inv_cdf(1 - alpha / 2) * math.sqrt(max(var_s, 0.0))
    m1 = (n - c) / 2
    m2 = (n + c) / 2
    return SenSlope(statistics.median(slopes), _at_rank(slopes, m1), _at_rank(slopes, m2 + 1), n)


@dataclass(frozen=True)
class Trend:
    n: int
    p: float
    slope: float
    low: float
    high: float
    notable: bool


def trend(
    points: Sequence[tuple[float, float]], *, min_n: int, alpha: float = ALPHA
) -> Trend | None:
    """Mann-Kendall + Sen over (t, x) points in time order. None below min_n."""
    if len(points) < min_n:
        return None
    mk = mann_kendall([x for _, x in points])
    if mk is None:
        return None
    sen = sen_slope(points, mk.var_s, alpha)
    if sen is None:
        return None
    excludes_zero = sen.low > 0 or sen.high < 0
    return Trend(mk.n, mk.p, sen.slope, sen.low, sen.high, mk.p < alpha and excludes_zero)


@dataclass(frozen=True)
class Baseline:
    median: float
    mad: float
    low: float
    high: float
    n: int


def own_baseline(prior: Sequence[float], *, min_n: int = 7, k: float = 2.0) -> Baseline | None:
    """The own usual range, median +/- k * 1.4826 * MAD of the prior values. None below min_n or
    when the MAD is 0 (no spread yet)."""
    if len(prior) < min_n:
        return None
    med = statistics.median(prior)
    mad = statistics.median(abs(x - med) for x in prior)
    if mad == 0:
        return None
    half = k * MAD_SCALE * mad
    return Baseline(med, mad, med - half, med + half, len(prior))


def outside(x: float, b: Baseline, side: str = "both") -> bool:
    """True when x lies outside the range on the given side ("both", "low" or "high")."""
    if side == "low":
        return x < b.low
    if side == "high":
        return x > b.high
    return x < b.low or x > b.high


def time_to_limit(
    current: float, slope_low: float, slope_high: float, limit: float, *, max_h: float = 12.0
) -> tuple[float, float] | None:
    """Hours to reach `limit` at the slope interval's two ends (slopes per hour). None when the
    interval includes 0, points away from the limit, or the far end is beyond max_h."""
    d = limit - current
    if slope_low <= 0 <= slope_high:
        return None
    if d == 0:
        return (0.0, 0.0)
    if (d > 0) != (slope_low > 0):
        return None
    a, b = d / slope_high, d / slope_low
    low, high = min(a, b), max(a, b)
    if high > max_h:
        return None
    return (low, high)


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


@dataclass(frozen=True)
class Spearman:
    n: int
    rho: float
    low: float
    high: float


def spearman(
    pairs: Sequence[tuple[float, float]], *, min_n: int = 20, alpha: float = ALPHA
) -> Spearman | None:
    """Spearman rho with a Fisher-z interval. None below min_n or when a side has no spread."""
    n = len(pairs)
    if n < min_n:
        return None
    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    if len(set(rx)) < 2 or len(set(ry)) < 2:
        return None
    rho = statistics.correlation(rx, ry)
    r = max(min(rho, 0.999999), -0.999999)
    z = math.atanh(r)
    half = _N.inv_cdf(1 - alpha / 2) * 1.03 / math.sqrt(n - 3)
    # A perfect rank order (rho = +/-1) is clamped for atanh; the interval still contains rho.
    return Spearman(n, rho, min(math.tanh(z - half), rho), max(math.tanh(z + half), rho))


def lagged_pairs(xs: dict, ys: dict, *, lag: timedelta) -> list[tuple]:
    """(key, x at key, y at key + lag) for every key where both exist; keys are dates or datetimes.
    A missing side drops the pair: nothing is filled."""
    out = []
    for d in sorted(xs):
        y = ys.get(d + lag)
        if y is not None:
            out.append((d, xs[d], y))
    return out
