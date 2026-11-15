# Signals Module (D45) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the habitat hub's cross-reference and labelled-trend signals module: 19 signals computed on read, shown on a new console screen, with a self-check trigger that never raises an alert.

**Architecture:** A feature-gated package `hub/signals/` computes every signal on read from the store: pure statistics (`methods.py`), store-to-series inputs (`inputs.py`), one builder module per data family, and a thin `engine.py`. `GET /api/signals` serves them. A 5-minute trigger opens a self-check prompt on a steady-to-notable change. Two reference feeds (ISS Live atmosphere and outdoor Earth weather) become stored, quiet readings first.

**Tech Stack:** Python 3.12 (FastAPI, SQLite, standard-library statistics only), TypeScript (Vite, vitest, jsdom), ruff.

**Spec:** `docs/decisions/2026-11-15-signals-module-design.md` (D45, PR alefnsc/habitat-health-monitor#37, approved by the team owner on 2026-11-15). Read it before starting; this plan argues from it.

**Where to work:** post-event only. Start from `origin/main` after PR #37 merges. One branch and one draft PR per slice (six PRs). Never edit the bench's main checkout: the live hub runs from it; work in a separate worktree. Run Python commands from the repo root with the project's venv active; run console commands with `npm --prefix console`. Never merge a PR yourself: the team owner merges.

**How this plan was checked:** every code block and diff below was applied task by task to a copy of `origin/main` at `239924d`, and the full Python suites, ruff, the console typecheck, build and vitest were run after each task. The "expected" outputs are from those runs. Tasks 1–12 were checked after each task in the final run; tasks 13–18 were checked after each task in an earlier run (before two tests were added to Tasks 2 and 10), and the trees after Tasks 6, 15 and 18 were checked again in full after the 2026-11-15 decisions (ISS 30-minute blocks, INMET wording). Hub tests go from 871 to 951 (`-m 'not broker'`) and console tests from 261 to 268, with no new failures; the one failure on both sides is `test_firmware_tilt.py::test_readme_safety_and_no_company_name`, which needs a git checkout (test-gap analysis item 7). Task 9 (INMET) has no run output yet: it needs the token and the live server.

## Global Constraints

Every task's requirements include these. Values are copied from the spec.

- No diagnosis and no clinical claims. Estimates are labelled, never "measured", "validated" or "accurate".
- No single kcal figure and no "energy balance". Camera joules and food kcal are never added, subtracted or converted, and no catalogue entry takes both a rep input and an intake input in one value.
- Wording is fixed by kind: "trend", "own usual range", "at this rate", "if nothing changes", "side by side". Signal copy passes `rulePrediction`, which bans "predict", "prediction", "forecast", "risk" and "will"; "not a prediction" is allowed.
- Missing data stays missing: no interpolation, no imputation, no carrying a value forward. A day with no meal logged has no intake value, not zero.
- No bare number: every estimate has a `low`–`high` interval; otherwise the state is `not_enough_data` with `missing` saying what is needed.
- Replay and real rows never pool in one signal: real rows win in a window; replay rows are used only when the window has no real row.
- Signals never write a reading, an assessment, an alert or a command, and never cross the link. Only the crew's self-check answer crosses, as answers do today, with no signal values.
- Body data goes public only with signed adult consent (`PUBLIC_CREWS`). R5: no company or vendor name in code or console text (vendors only in `DATA_SOURCES.md`). R8: no data of the minor team member; the synthetic crews are `crew-a` and `crew-c` only, never `crew-b`.
- Statistics use the Python standard library only (`math`, `statistics`); no numpy or scipy.
- α = 0.05. Trend: n ≥ 10 blocks and ≥ 75 % coverage; notable when p < 0.05 and the Sen interval excludes 0. Baseline: ≥ 7 of the previous 14 days, today excluded; range median ± 2 × 1.4826 × MAD; notable only two days in a row outside. Time-to-limit: last 2 h of 5-minute medians, ≥ 18 of 24 blocks, limits read from the loaded rules by `rule_id`, horizon ≤ 12 h, notable when the near end is under 3 h. Lagged pairs: Spearman ρ only at ≥ 20 pairs, Fisher-z SE 1.03/√(n − 3), never notable.
- The bench location is a 1-decimal grid cell in `.env`; it is never committed, posted, logged or shown.
- Python style: ruff, line length 100; dense literals carry `# fmt: skip` as the rest of the repo does. Console copy is English only and lives in `console/src/copy.ts`.

## Decisions made while planning

The spec left these open or was silent. Each is small; the team owner may change any of them before a slice starts.

1. **Text is keys only.** `limits` and `missing` are copy keys worded in `console/src/copy.ts` (spec §5 spoke of "the hub's `limits` strings"); all text stays where the honesty lint already runs.
2. **Reference feeds are quiet.** The six `iss_*` and `earth_*` indicators form `REFERENCE_INDS`. Ingest treats them like `load_raw` (stored; not assessed, outboxed or pushed) and `status_body` skips them, so `/api/status`, the link and the public page stay exactly as they are (spec §4.3). No threshold rule exists for them, so no judgement is lost.
3. **ISS units: confirmed by the team owner (2026-11-15).** The table the hub already serves (`hub/nasa/isslive_routes.py`): pressure in mmHg (the feed mislabels it PSI; the capture reads about 758.6), stored in hPa; temperature in C (about 23.5); both ppCO2 items in mmHg (2.4 and 2.95; the feed's PSIA label cannot be right).
4. **Replay signals never open a self-check.** Synthetic data does not ask a real crew how they feel. Their state changes are still logged.
5. **Signal prompts need a snapshot.** `PromptService.create` refuses `signal_cabin` and `signal_body` without a `trigger`, so `POST /api/prompts` cannot make one by hand.
6. **No prompts screen.** The console has none today (the nav item says "built in a later task"), so the spec's "self-check popup" is a line on the signal's own card: "A self-check is open for this signal." A prompts screen is out of scope.
7. **Lift signals say "not enough data" on the replay.** `hub.sim` cannot create camera sessions, so the replay file has no sets; the lift tests use direct sessions.
8. **The replay lands in slice 2 without outdoor-temperature lines** (`earth_temp` exists from slice 3). Task 8 adds them and regenerates the file.
9. **Windows the spec did not give:** 60 days for the lift and lagged-pair signals; `lift_work_sets` follows one exercise, the latest set's.
10. **`body_mass_30d` uses the global trend rule** (≥ 10 days and 75 % of 30 days, so 23 days with a weigh-in). Fewer weigh-ins give "not enough data". The panel's arithmetic weigh-in line is unchanged.
11. **Both ISS CO2 items are stored as `iss_ppco2`**, as the spec says; the ISS trend's limit line names "the lab and Node 3 ppCO2 items together".
12. **The weather importer refuses to fetch** until the provider adapter (Task 9) exists.
13. **ISS ppCO2 uses 30-minute blocks** (team owner, 2026-11-15): ISS Live pushes a value only when it changes (2 updates in the 13-minute capture), so 10-minute blocks would often be empty. Twelve blocks over 6 h keep n ≥ 10 and 75 % coverage; no value is repeated or filled.
14. **The provider is INMET automatic stations** (team owner, 2026-11-15), not a weather model: observed, raw, unvalidated hourly data from the nearest public station. Open-Meteo was dropped because its licence asks for a credit link next to the displayed data, against the vendor-free console text. The station's code stays in `.env` like the location.

## File map

| File | Responsibility | Task |
|---|---|---|
| `hub/signals/methods.py` | Mann-Kendall, Sen slope and interval, median/MAD baseline, time-to-limit, Spearman + Fisher z, lagged pairing. Pure. | 1 |
| `hub/signals/types.py` | The `Signal` object and its parts. No text. | 2 |
| `hub/signals/catalogue.py` | The 19 signals as `Spec` data; limit copy keys. | 2, 6, 10–12 |
| `hub/signals/inputs.py` | Store rows to points and blocks; real-or-replay choice; nights from `sleep_h`; nightly resting HR. | 2 |
| `hub/signals/common.py` | `Ctx`, the `Signal` constructors and the shared trend path. | 2 |
| `hub/signals/cabin.py` | 6-hour cabin, ISS and Earth trends; time-to-limit. | 2 |
| `hub/signals/body.py` | Nightly values, own-baseline ranges, 14-night trends. | 2 |
| `hub/signals/engine.py` | `BUILDERS` dispatch and `evaluate()`. | 2, 10–12 |
| `hub/signals/routes.py` | `GET /api/signals`, `GET /api/signals/{id}`. | 3 |
| `hub/sim/signals_synth.py` | The 28-day synthetic replay generator. | 4, 8 |
| `data/replay/signals-synthetic-28d.jsonl` | Generated replay (never hand-edited). | 4, 8 |
| `hub/nasa/iss_store.py` | ISS Live items to quiet reference readings. | 7 |
| `nodes/weather/` | Outdoor weather importer: mapper, coarse location, provider seam, CLI. | 8, 9 |
| `hub/signals/daily.py` | Daily body-mass and water-logged trends. | 10 |
| `hub/signals/lift.py` | Camera-set rollups and the three lift signals. | 11 |
| `hub/signals/pairs.py` | The four lagged cross-references. | 12 |
| `hub/signals/trigger.py` | The self-check trigger and `signal_events`. | 14 |
| `console/src/model/signals.ts` | Wording of signal objects from copy keys. | 15 |
| `console/src/views/signals.ts` | The `#/signals` screen. | 16 |
| `console/src/views/panel/topbar.ts` | The "Signals: N notable" chip. | 17 |

---

## Slice 1: statistics (PR 1)

Branch `feat/d45-signals-methods` from `origin/main`. One task. No wiring: nothing changes for a running hub.

### Task 1: Signal statistics (methods.py)

The statistics every signal uses. Pure functions: no store, no clock, no I/O. Each returns `None` when it cannot answer honestly; the engine turns that into `not_enough_data`.

**Files:**
- Create: `hub/signals/__init__.py`
- Create: `hub/signals/methods.py`
- Create: `hub/tests/signals/__init__.py`
- Create: `hub/tests/signals/test_methods.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`hub/signals/methods.py`):
  - `ALPHA = 0.05`, `MAD_SCALE = 1.4826`; reference strings `MK_REF`, `SEN_REF`, `BASELINE_REF`, `TTL_REF`, `SPEARMAN_REF`.
  - `mann_kendall(xs: Sequence[float]) -> MannKendall | None` (fields `n, s, var_s, z, p`; `None` below 3 points).
  - `sen_slope(points: Sequence[tuple[float, float]], var_s: float, alpha=ALPHA) -> SenSlope | None` (`slope, low, high, n_slopes`).
  - `trend(points, *, min_n: int, alpha=ALPHA) -> Trend | None` (`n, p, slope, low, high, notable`).
  - `own_baseline(prior: Sequence[float], *, min_n=7, k=2.0) -> Baseline | None` (`median, mad, low, high, n`); `outside(x, b, side="both"|"low"|"high") -> bool`.
  - `time_to_limit(current, slope_low, slope_high, limit, *, max_h=12.0) -> tuple[float, float] | None`.
  - `spearman(pairs, *, min_n=20, alpha=ALPHA) -> Spearman | None` (`n, rho, low, high`).
  - `lagged_pairs(xs: dict, ys: dict, *, lag: timedelta) -> list[tuple]` (`(key, x, y)` where both sides exist).

- [ ] **Step 1: Write the failing tests**

Create `hub/tests/signals/__init__.py` (empty file).

Create `hub/tests/signals/test_methods.py`:

```python
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
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_methods.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'hub.signals'
1 error in 0.11s
```

- [ ] **Step 3: Write the implementation**

The expected values in the tests are worked by hand from the formulas (see the test's docstring). If you have Gilbert (1987) ch. 16 at hand, you may add its worked example as an extra test; the hand values must still pass.

Create `hub/signals/__init__.py` (empty file).

Create `hub/signals/methods.py`:

```python
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
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_methods.py
```

Expected:

```text
17 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/signals/__init__.py hub/signals/methods.py hub/tests/signals/__init__.py hub/tests/signals/test_methods.py
git commit -m "feat(signals): statistics for D45 signals (Mann-Kendall, Sen, MAD baseline, time-to-limit, Spearman)"
```

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat(signals): D45 statistics" --body "Implements D45 slice 1 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 1."
```

---

## Slice 2: engine, API and replay for the cabin and body signals (PR 2)

Branch `feat/d45-signals-engine` from `origin/main` after PR 1 merges (or stacked on it). Adds the `signals` feature:
nine signals (cabin trends, three time-to-limit, ring baselines, the 14-night HR trend), `GET /api/signals`, and the
synthetic replay.

### Task 2: Signal engine: cabin and nightly body signals

The `Signal` object, the catalogue, the inputs and the cabin and nightly-body builders. `evaluate()` returns cabin signals once (crew `None`) and body signals once per crew.

**Files:**
- Create: `hub/signals/types.py`
- Create: `hub/signals/catalogue.py`
- Create: `hub/signals/inputs.py`
- Create: `hub/signals/common.py`
- Create: `hub/signals/cabin.py`
- Create: `hub/signals/body.py`
- Create: `hub/signals/engine.py`
- Create: `hub/tests/signals/test_engine_cabin_body.py`

**Interfaces:**
- Consumes: Task 1's `methods`; `Store.readings_between`, `hub.assess.CREW_SCOPED`, `hub.thresholds.Rule`.
- Produces:
  - `hub/signals/types.py`: `Input`, `Value(estimate, low, high, unit, per)`, `Method`, `Missing(key, need, have)`, `Signal` (fields in the spec §5 plus `series`, `pairs`, `can_trigger`, `detail`; `to_dict()`).
  - `hub/signals/catalogue.py`: `Spec(id, kind, source, ind, window, block, min_n, coverage, per_crew, can_trigger, rule_id, side, limits, unit)`, `CATALOGUE`, `BY_ID`, and the `signals.limit.*` key constants.
  - `hub/signals/inputs.py`: `ok_rows`, `choose`, `same_mode`, `describe`, `points`, `block_medians`, `expected_blocks`, `trailing_mean`, `hours_since`, `series_out`, `Night`, `nights`, `night_rest_hr`, `HOUR`, `DAY`.
  - `hub/signals/common.py`: `Ctx(store, rules, at, tz)`, `unit_of`, `spec_unit`, `need_for`, `method`, `signal`, `nodata`, `trend_headline`, `trend_signal`.
  - `hub/signals/cabin.py`: `blocked`, `cabin_trend`, `time_to_limit`. `hub/signals/body.py`: `nightly(ctx, source, ind, crew, days)`, `baseline`, `night_trend`.
  - `hub/signals/engine.py`: `BUILDERS: dict[(kind, source), Builder]`, `evaluate_spec`, `evaluate(store, rules, *, crews, at, tz, ids=None) -> list[Signal]`.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/signals/test_engine_cabin_body.py`:

```python
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
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_engine_cabin_body.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'hub.signals.engine'
1 error in 0.11s
```

- [ ] **Step 3: Write the implementation**

Headline keys used by the builders: `signals.trend.up|down|flat`, `signals.ttl.reaches|none|away|outside`, `signals.baseline.above|below|inside`, `signals.nodata`. Missing keys: `signals.missing.blocks|nights|priorDays|spread|recentNight|rule`. The console words them in Task 15.

Create `hub/signals/types.py`:

```python
"""The Signal object (D45 §5). Text is never built here: the console turns keys into words."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Kind = Literal["trend", "baseline", "time_to_limit", "lagged_pair"]
State = Literal["notable", "steady", "not_enough_data"]


@dataclass(frozen=True)
class Input:
    ind: str
    src: str
    dev: str
    node: str
    n: int
    first_at: str
    last_at: str
    oldest_age_s: float


@dataclass(frozen=True)
class Value:
    estimate: float
    low: float
    high: float
    unit: str
    per: str | None = None


@dataclass(frozen=True)
class Method:
    name: str
    ref: str
    alpha: float | None
    n: int
    min_n: int
    window_start: str
    window_end: str
    coverage: float | None


@dataclass(frozen=True)
class Missing:
    key: str
    need: int | None = None
    have: int | None = None


@dataclass(frozen=True)
class Signal:
    id: str
    kind: Kind
    crew: str | None
    state: State
    headline_key: str
    value: Value | None
    method: Method
    inputs: list[Input] = field(default_factory=list)
    missing: list[Missing] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    reference: dict | None = None
    replay: bool = False
    series: list[list] = field(default_factory=list)  # [[iso time, value], ...] blocked points
    pairs: list[list] = field(default_factory=list)  # lagged pairs only: [[key, x, y], ...]
    can_trigger: bool = False
    detail: dict = field(default_factory=dict)  # kind-specific extras, e.g. one entry per lag

    def to_dict(self) -> dict:
        return asdict(self)
```

Create `hub/signals/catalogue.py`:

```python
"""The v1 signal catalogue as data (D45 §7). The engine dispatches on (kind, source)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from hub.signals.types import Kind

MIN = timedelta(minutes=1)
H = timedelta(hours=1)
D = timedelta(days=1)

INDEPENDENCE = "signals.limit.independence"
BENCH = "signals.limit.benchSensor"
STRAIGHT = "signals.limit.straightLine"
RING = "signals.limit.ringEstimate"
REST_ONLY = "signals.limit.restOnly"
OWN_DATA = "signals.limit.ownData"
ISS = "signals.limit.issTelemetry"
EARTH = "signals.limit.earthReference"
NEIGHBOUR_HOURS = "signals.limit.neighbourHours"
CAMERA = "signals.limit.cameraEstimate"
NOT_FOOD = "signals.limit.notFoodEnergy"
RIG_CHECK = "signals.limit.rigCheck"
ON_EARTH = "signals.limit.onEarth"
LOGGED_ONLY = "signals.limit.loggedOnly"


@dataclass(frozen=True)
class Spec:
    id: str
    kind: Kind
    source: str  # "cabin", "cabin_mean_1h", "night_rest_hr", "night_value", ...
    ind: str | None
    window: timedelta
    block: timedelta | None
    min_n: int
    coverage: float  # share of expected blocks (or days) that must be present
    per_crew: bool  # True: one signal per crew; False: crew None (cabin, ISS, Earth)
    can_trigger: bool = False
    rule_id: str | None = None
    side: str = "both"  # baseline: which side of the range counts as notable
    limits: tuple[str, ...] = ()
    unit: str | None = None  # when the value is not in the indicator's own unit


CATALOGUE: tuple[Spec, ...] = (
    Spec("cabin_temp_6h", "trend", "cabin", "cabin_temp", 6 * H, 10 * MIN, 10, 0.75, False,
         limits=(INDEPENDENCE, BENCH)),
    Spec("cabin_rh_6h", "trend", "cabin", "cabin_rh", 6 * H, 10 * MIN, 10, 0.75, False,
         limits=(INDEPENDENCE, BENCH)),
    Spec("cabin_temp_ttl", "time_to_limit", "cabin", "cabin_temp", 2 * H, 5 * MIN, 18, 0.75, False,
         can_trigger=True, rule_id="cabin_health_box_temp", limits=(STRAIGHT, BENCH)),
    Spec("cabin_rh_ttl", "time_to_limit", "cabin", "cabin_rh", 2 * H, 5 * MIN, 18, 0.75, False,
         can_trigger=True, rule_id="cabin_health_box_rh", limits=(STRAIGHT, BENCH)),
    Spec("cabin_ppco2_ttl", "time_to_limit", "cabin_mean_1h", "cabin_ppco2", 2 * H, 5 * MIN, 18,
         0.75, False, can_trigger=True, rule_id="co2_1h", limits=(STRAIGHT,)),
    Spec("rest_hr_baseline", "baseline", "night_rest_hr", "hr", 14 * D, None, 7, 0.0, True,
         can_trigger=True, limits=(RING, REST_ONLY)),
    Spec("rest_hr_14n", "trend", "night_rest_hr", "hr", 14 * D, None, 10, 0.75, True,
         limits=(INDEPENDENCE, RING, REST_ONLY)),
    Spec("sleep_baseline", "baseline", "night_value", "sleep_h", 14 * D, None, 7, 0.0, True,
         can_trigger=True, limits=(RING,)),
    Spec("spo2_baseline", "baseline", "night_value", "spo2", 14 * D, None, 7, 0.0, True,
         can_trigger=True, side="low", limits=(RING,)),
)  # fmt: skip

BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
```

Create `hub/signals/inputs.py`:

```python
"""Store rows to the series the methods take (D45 §6.5). Only assessable rows; no gap is filled.

Replay and real rows never pool: `choose` keeps the real rows when any exist in the window, and the
replay rows only when the window has no real row.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from hub.assess import CREW_SCOPED
from hub.signals.types import Input
from hub.store import Store, StoredReading
from hub.timeutil import parse_iso, to_iso

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def ok_rows(
    store: Store, ind: str, start: datetime, end: datetime, crew: str | None
) -> list[StoredReading]:
    """Assessable rows of `ind` in (start, end], crew-scoped like the assessor."""
    rows = store.readings_between(ind, start, end, crew=crew, scope_crew=ind in CREW_SCOPED)
    return [r for r in rows if r.q == ("ok",)]


def choose(rows: Sequence[StoredReading]) -> tuple[list[StoredReading], bool]:
    """(rows to use, replay flag): the real rows if any exist, else the replay rows."""
    real = [r for r in rows if r.src != "replay"]
    if real:
        return real, False
    return list(rows), bool(rows)


def same_mode(rows: Sequence[StoredReading], replay: bool) -> list[StoredReading]:
    """Keep only rows of the chosen mode, so a second input follows the first input's choice."""
    return [r for r in rows if (r.src == "replay") == replay]


def describe(rows: Iterable[StoredReading], at: datetime) -> list[Input]:
    """One Input per (ind, src, dev, node) group, in first-seen order."""
    groups: dict[tuple[str, str, str, str], list[StoredReading]] = {}
    for r in rows:
        groups.setdefault((r.ind, r.src, r.dev, r.node), []).append(r)
    out = []
    for (ind, src, dev, node), rs in groups.items():
        times = sorted(r.measured_at for r in rs)
        oldest = (at - parse_iso(times[-1])).total_seconds()
        out.append(Input(ind, src, dev, node, len(rs), times[0], times[-1], max(0.0, oldest)))
    return out


def points(rows: Iterable[StoredReading]) -> list[tuple[datetime, float]]:
    return [(parse_iso(r.measured_at), r.val) for r in rows]


def block_medians(
    pts: Sequence[tuple[datetime, float]], start: datetime, end: datetime, block: timedelta
) -> list[tuple[datetime, float]]:
    """(block middle, median of the block's values) for every block in (start, end] that has a
    point. Empty blocks are absent, never zero."""
    buckets: dict[int, list[float]] = {}
    last = expected_blocks(start, end, block) - 1
    for t, v in pts:
        if not start < t <= end:
            continue
        buckets.setdefault(min(int((t - start) / block), last), []).append(v)
    return [(start + block * (i + 0.5), statistics.median(v)) for i, v in sorted(buckets.items())]


def expected_blocks(start: datetime, end: datetime, block: timedelta) -> int:
    return max(1, math.ceil((end - start) / block))


def trailing_mean(
    rows: Sequence[StoredReading], window: timedelta, coverage: timedelta
) -> list[tuple[datetime, float]]:
    """(t, mean of rows in (t - window, t]) at each row, as hub/assess.py judges a mean window:
    a row is skipped until the rows before it span `coverage`."""
    pts = points(rows)
    out = []
    lo, total = 0, 0.0
    for i, (t, v) in enumerate(pts):
        total += v
        while pts[lo][0] <= t - window:
            total -= pts[lo][1]
            lo += 1
        if t - pts[lo][0] >= coverage:
            out.append((t, total / (i + 1 - lo)))
    return out


def hours_since(t: datetime, origin: datetime) -> float:
    return (t - origin) / HOUR


def series_out(points: Sequence[tuple[datetime, float]]) -> list[list]:
    return [[to_iso(t), v] for t, v in points]


# Nights (ring sleep_h): the window is (sleep_end - sleep_h, sleep_end]


@dataclass(frozen=True)
class Night:
    day: date  # local date of the sleep end
    start: datetime
    end: datetime
    sleep_h: float
    row: StoredReading


def nights(
    store: Store, crew: str | None, end: datetime, days: int, tz: ZoneInfo
) -> tuple[list[Night], bool]:
    """The crew's nights ending in (end - days, end], one per local day (the latest end wins),
    ascending, with the replay flag of the chosen rows."""
    rows, replay = choose(ok_rows(store, "sleep_h", end - DAY * days, end, crew))
    by_day: dict[date, Night] = {}
    for r in rows:
        t_end = parse_iso(r.measured_at)
        n = Night(t_end.astimezone(tz).date(), t_end - HOUR * r.val, t_end, r.val, r)
        cur = by_day.get(n.day)
        if cur is None or n.end > cur.end:
            by_day[n.day] = n
    return [by_day[d] for d in sorted(by_day)], replay


REST_BLOCK = timedelta(minutes=5)
REST_COVERAGE = 0.5


def night_rest_hr(
    store: Store, crew: str | None, night: Night, replay: bool
) -> tuple[float | None, list[StoredReading]]:
    """Median of the 5-minute HR block medians inside the night window, or None below 50 % of
    the window's blocks. Returns the HR rows used, for the inputs list."""
    rows = same_mode(ok_rows(store, "hr", night.start, night.end, crew), replay)
    blocks = block_medians(points(rows), night.start, night.end, REST_BLOCK)
    if len(blocks) < REST_COVERAGE * expected_blocks(night.start, night.end, REST_BLOCK):
        return None, rows
    return statistics.median(v for _, v in blocks), rows
```

Create `hub/signals/common.py`:

```python
"""Shared pieces of the signal builders: the evaluation context and the Signal constructors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from hub.contract import DERIVED, INDICATORS
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.types import Method, Missing, Signal, Value
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import to_iso

TREND_REF = M.MK_REF + "; " + M.SEN_REF


@dataclass(frozen=True)
class Ctx:
    store: Store
    rules: dict[str, Rule]
    at: datetime
    tz: ZoneInfo


def unit_of(ind: str | None) -> str:
    return INDICATORS.get(ind or "") or DERIVED.get(ind or "", "")


def spec_unit(spec: Spec) -> str:
    return spec.unit or unit_of(spec.ind)


def need_for(spec: Spec, expected: int) -> int:
    """Points needed: at least min_n, and at least `coverage` of the expected points."""
    return max(spec.min_n, math.ceil(spec.coverage * expected))


def method(
    spec: Spec, ctx: Ctx, name: str, ref: str, n: int, start: datetime,
    coverage: float | None, alpha: float | None = M.ALPHA,
) -> Method:  # fmt: skip
    return Method(name, ref, alpha, n, spec.min_n, to_iso(start), to_iso(ctx.at), coverage)


def signal(
    spec: Spec, crew: str | None, state: str, headline: str, value: Value | None, meth: Method,
    **kw,
) -> Signal:  # fmt: skip
    return Signal(
        spec.id, spec.kind, crew, state, headline, value, meth,  # type: ignore[arg-type]
        limits=list(spec.limits), can_trigger=spec.can_trigger, **kw,
    )  # fmt: skip


def nodata(spec: Spec, crew: str | None, meth: Method, missing: list[Missing], **kw) -> Signal:
    return signal(spec, crew, "not_enough_data", "signals.nodata", None, meth, missing=missing,
                  **kw)  # fmt: skip


def trend_headline(t: M.Trend) -> str:
    if not t.notable:
        return "signals.trend.flat"
    return "signals.trend.up" if t.slope > 0 else "signals.trend.down"


def trend_signal(
    spec: Spec, ctx: Ctx, crew: str | None, pts: list[tuple[float, float]], expected: int,
    start: datetime, per: str, missing_key: str, **common,
) -> Signal:  # fmt: skip
    """The shared trend path: `pts` are (t in `per` units since start, value)."""
    need = need_for(spec, expected)
    meth = method(spec, ctx, "mann_kendall_sen", TREND_REF, len(pts), start, len(pts) / expected)
    if len(pts) < need:
        return nodata(spec, crew, meth, [Missing(missing_key, need, len(pts))], **common)
    t = M.trend(pts, min_n=spec.min_n)
    if t is None:
        return nodata(spec, crew, meth, [Missing(missing_key, need, len(pts))], **common)
    value = Value(t.slope, t.low, t.high, spec_unit(spec), per)
    return signal(spec, crew, "notable" if t.notable else "steady", trend_headline(t), value,
                  meth, **common)  # fmt: skip
```

Create `hub/signals/cabin.py`:

```python
"""Cabin, ISS and Earth series (crew None): 6-hour trends and the time-to-limit (D45 §6.1, §6.3)."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from hub.signals import inputs as I
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, need_for, nodata, signal, trend_signal
from hub.signals.types import Missing, Signal, Value
from hub.store import StoredReading

TTL_NOTABLE_H = 3.0
MEAN_1H_COVERAGE = timedelta(seconds=2700)  # as hub/assess.py: 45 minutes of a 1-hour window


def blocked(ctx: Ctx, spec: Spec) -> tuple[list[StoredReading], bool, list[tuple[datetime, float]]]:
    """(rows used, replay flag, block medians) of the spec's series over its window."""
    start = ctx.at - spec.window
    assert spec.ind is not None and spec.block is not None
    if spec.source == "cabin_mean_1h":
        # co2_1h judges a 1-hour mean: fit the trailing mean, built from an hour before the window.
        rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start - I.HOUR, ctx.at, None))
        pts = I.trailing_mean(rows, I.HOUR, MEAN_1H_COVERAGE)
    else:
        rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start, ctx.at, None))
        pts = I.points(rows)
    return rows, replay, I.block_medians(pts, start, ctx.at, spec.block)


def cabin_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    rows, replay, blocks = blocked(ctx, spec)
    common = {"inputs": I.describe(rows, ctx.at), "replay": replay, "series": I.series_out(blocks)}
    pts = [(I.hours_since(t, start), v) for t, v in blocks]
    expected = I.expected_blocks(start, ctx.at, spec.block)
    return trend_signal(spec, ctx, crew, pts, expected, start, "h", "signals.missing.blocks",
                        **common)  # fmt: skip


def time_to_limit(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    rows, replay, blocks = blocked(ctx, spec)
    expected = I.expected_blocks(start, ctx.at, spec.block)
    meth = method(spec, ctx, "sen_time_to_limit", M.TTL_REF, len(blocks), start,
                  len(blocks) / expected)  # fmt: skip
    common = {"inputs": I.describe(rows, ctx.at), "replay": replay, "series": I.series_out(blocks)}
    rule = ctx.rules.get(spec.rule_id or "")
    if rule is None or rule.ok is None:
        return nodata(spec, crew, meth, [Missing("signals.missing.rule")], **common)
    need = need_for(spec, expected)
    if len(blocks) < need:
        return nodata(spec, crew, meth, [Missing("signals.missing.blocks", need, len(blocks))],
                      **common)  # fmt: skip
    pts = [(I.hours_since(t, start), v) for t, v in blocks]
    mk = M.mann_kendall([v for _, v in pts])
    sen = M.sen_slope(pts, mk.var_s) if mk else None
    if sen is None:
        return nodata(spec, crew, meth, [Missing("signals.missing.blocks", need, len(blocks))],
                      **common)  # fmt: skip
    current = statistics.median(v for _, v in blocks[-3:])
    reference: dict = {"rule_id": rule.id, "source_kind": rule.source_kind, "limit": None}
    if not rule.ok.contains(current):
        # Already outside: the assessor's band status says so; no time is shown.
        return signal(spec, crew, "steady", "signals.ttl.outside", None, meth, reference=reference,
                      **common)  # fmt: skip
    limit = rule.ok.max if sen.slope > 0 else rule.ok.min
    if limit is None:
        return signal(spec, crew, "steady", "signals.ttl.away", None, meth, reference=reference,
                      **common)  # fmt: skip
    reference["limit"] = limit
    hours = M.time_to_limit(current, sen.low, sen.high, limit)
    if hours is None:
        return signal(spec, crew, "steady", "signals.ttl.none", None, meth, reference=reference,
                      **common)  # fmt: skip
    mid = (limit - current) / sen.slope if sen.slope else hours[1]
    value = Value(min(max(mid, hours[0]), hours[1]), hours[0], hours[1], "h")
    state = "notable" if hours[0] < TTL_NOTABLE_H else "steady"
    return signal(spec, crew, state, "signals.ttl.reaches", value, meth, reference=reference,
                  **common)  # fmt: skip
```

Create `hub/signals/body.py`:

```python
"""Nightly body values (per crew): own-baseline ranges and 14-night trends (D45 §6.1, §6.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from hub.signals import inputs as I
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal, spec_unit, trend_signal
from hub.signals.types import Missing, Signal, Value
from hub.store import StoredReading

RECENT_NIGHT = timedelta(hours=36)
BASELINE_DAYS = 14
FETCH_DAYS = 31  # the latest night, the night before, and 14 prior nights for each


def nightly(
    ctx: Ctx, source: str, ind: str, crew: str | None, days: int
) -> tuple[dict[date, tuple[datetime, float]], list[StoredReading], bool]:
    """{local day of the night's end: (night end, value)}, the rows used, and the replay flag.
    `source` "night_rest_hr" gives the nightly resting HR; else `ind` is read per night."""
    nights, replay = I.nights(ctx.store, crew, ctx.at, days, ctx.tz)
    out: dict[date, tuple[datetime, float]] = {}
    used: list[StoredReading] = [n.row for n in nights]
    if source == "night_rest_hr":
        for n in nights:
            v, rows = I.night_rest_hr(ctx.store, crew, n, replay)
            used += rows
            if v is not None:
                out[n.day] = (n.end, v)
    elif ind == "sleep_h":
        out = {n.day: (n.end, n.sleep_h) for n in nights}
    else:  # a nightly reading timed at the night's end (spo2), matched to that night
        rows = I.same_mode(I.ok_rows(ctx.store, ind, ctx.at - I.DAY * days, ctx.at, crew),
                           replay)  # fmt: skip
        night_days = {n.day for n in nights}
        for t, v in I.points(rows):
            d = t.astimezone(ctx.tz).date()
            if d in night_days:
                out[d] = (t, v)
        used += rows
    return out, used, replay


def baseline(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    values, used, replay = nightly(ctx, spec.source, spec.ind or "", crew, FETCH_DAYS)
    start = ctx.at - spec.window
    pts = sorted(values.values())
    common = {"inputs": I.describe(used, ctx.at), "replay": replay, "series": I.series_out(pts)}
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, 0, start, None, alpha=None)
    if not values or ctx.at - max(values.values())[0] > RECENT_NIGHT:
        return nodata(spec, crew, meth, [Missing("signals.missing.recentNight")], **common)
    today = max(values)

    def range_for(day: date) -> tuple[M.Baseline | None, int]:
        prior = [
            v for d, (_, v) in values.items() if day - timedelta(days=BASELINE_DAYS) <= d < day
        ]
        return M.own_baseline(prior, min_n=spec.min_n), len(prior)

    b, n_prior = range_for(today)
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, n_prior, start, None, alpha=None)
    if b is None:
        key = "signals.missing.priorDays" if n_prior < spec.min_n else "signals.missing.spread"
        return nodata(spec, crew, meth, [Missing(key, spec.min_n, n_prior)], **common)
    x = values[today][1]
    value = Value(x, b.low, b.high, spec_unit(spec))
    if x > b.high:
        headline = "signals.baseline.above"
    elif x < b.low:
        headline = "signals.baseline.below"
    else:
        headline = "signals.baseline.inside"
    # Notable only when the night before was outside its own range on the same side, too.
    yesterday = today - timedelta(days=1)
    notable = False
    if M.outside(x, b, spec.side) and yesterday in values:
        yb, _ = range_for(yesterday)
        notable = yb is not None and M.outside(values[yesterday][1], yb, spec.side)
    return signal(spec, crew, "notable" if notable else "steady", headline, value, meth, **common)


def night_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    values, used, replay = nightly(ctx, spec.source, spec.ind or "", crew, spec.window.days)
    start = ctx.at - spec.window
    ends = sorted(values.values())
    common = {"inputs": I.describe(used, ctx.at), "replay": replay, "series": I.series_out(ends)}
    pts = [((t - start) / I.DAY, v) for t, v in ends]
    return trend_signal(spec, ctx, crew, pts, spec.window.days, start, "day",
                        "signals.missing.nights", **common)  # fmt: skip
```

Create `hub/signals/engine.py`:

```python
"""Signals computed on read (D45 §4.1). evaluate() never writes to the store."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from hub.signals import body, cabin
from hub.signals.catalogue import BY_ID, CATALOGUE, Spec
from hub.signals.common import Ctx
from hub.signals.types import Signal
from hub.store import Store
from hub.thresholds import Rule

log = logging.getLogger("hub.signals")

Builder = Callable[[Ctx, Spec, str | None], Signal]
BUILDERS: dict[tuple[str, str], Builder] = {
    ("trend", "cabin"): cabin.cabin_trend,
    ("time_to_limit", "cabin"): cabin.time_to_limit,
    ("time_to_limit", "cabin_mean_1h"): cabin.time_to_limit,
    ("baseline", "night_rest_hr"): body.baseline,
    ("baseline", "night_value"): body.baseline,
    ("trend", "night_rest_hr"): body.night_trend,
}


def evaluate_spec(ctx: Ctx, spec: Spec, crew: str | None) -> Signal | None:
    """One signal, or None when its builder failed (logged; the other signals are unaffected)."""
    try:
        return BUILDERS[(spec.kind, spec.source)](ctx, spec, crew if spec.per_crew else None)
    except Exception:
        log.exception("signal %s failed for crew %s", spec.id, crew)
        return None


def evaluate(
    store: Store, rules: Sequence[Rule], *, crews: Sequence[str], at: datetime, tz: str,
    ids: Sequence[str] | None = None,
) -> list[Signal]:  # fmt: skip
    """Cabin signals once (crew None), body signals once per crew in `crews`, in catalogue order."""
    ctx = Ctx(store, {r.id: r for r in rules}, at, ZoneInfo(tz))
    specs = [BY_ID[i] for i in ids] if ids is not None else list(CATALOGUE)
    out: list[Signal] = []
    for spec in specs:
        for crew in crews if spec.per_crew else [None]:
            s = evaluate_spec(ctx, spec, crew)
            if s is not None:
                out.append(s)
    return out
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_engine_cabin_body.py
```

Expected:

```text
11 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/signals/body.py hub/signals/cabin.py hub/signals/catalogue.py hub/signals/common.py hub/signals/engine.py hub/signals/inputs.py hub/signals/types.py hub/tests/signals/test_engine_cabin_body.py
git commit -m "feat(signals): engine with cabin trends, time-to-limit and nightly body signals"
```

### Task 3: GET /api/signals and the `signals` feature gate

Serve the signals and gate them behind a new `signals` feature, on by default like the others. A broken `hub.signals` import leaves the hub starting.

**Files:**
- Create: `hub/signals/routes.py`
- Create: `hub/tests/signals/test_routes.py`
- Modify: `hub/config.py`
- Modify: `hub/tests/test_config.py`
- Modify: `hub/features.py`

**Interfaces:**
- Consumes: Task 2's `evaluate`, `BY_ID`; `hub.features` wiring (`_TABLE`, `_guard`, `HubContext`).
- Produces:
  - `GET /api/signals?crew=&at=` → `{"crew", "at", "signals": [Signal.to_dict()]}`; without `crew`, body signals for every crew in `settings.crews`.
  - `GET /api/signals/{id}?crew=&at=` → `{"at", "signals": [...]}`.
  - Errors: 422 `bad_crew`, 422 `bad_value:at` (not an aware ISO time), 404 `unknown_signal`, 503 `signals_off`.
  - `hub/signals/routes.py`: `router`, `SignalsState(store, rules, crews, tz, clock)`; `app.state.signals`.
  - `FEATURE_NAMES` gains `"signals"`.

- [ ] **Step 1: Write the failing tests**

Create `hub/tests/signals/test_routes.py`:

```python
import logging
import sys
from dataclasses import replace

from fastapi.testclient import TestClient

from hub.api import create_app


def app_with(settings, clock, features=frozenset({"signals"})):
    return create_app(replace(settings, features=features), clock=clock)


def test_signals_lists_cabin_once_and_body_per_crew(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals").json()
    ids = [(s["id"], s["crew"]) for s in body["signals"]]
    assert ("cabin_temp_6h", None) in ids
    assert {crew for i, crew in ids if i == "rest_hr_baseline"} == set(settings.crews)
    assert all(s["state"] == "not_enough_data" for s in body["signals"])  # an empty hub


def test_signals_crew_filter_and_at(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals", params={"crew": "crew-a", "at": "2026-11-14T09:00:00Z"}).json()
    assert body["crew"] == "crew-a" and body["at"] == "2026-11-14T09:00:00.000Z"
    assert {s["crew"] for s in body["signals"]} == {None, "crew-a"}


def test_signals_rejects_bad_crew_bad_at_unknown_id(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        assert c.get("/api/signals", params={"crew": "crew-z"}).json() == {"reason": "bad_crew"}
        assert c.get("/api/signals", params={"at": "2026-11-14T09:00:00"}).status_code == 422
        assert c.get("/api/signals/nope").status_code == 404


def test_one_signal(settings, clock):
    with TestClient(app_with(settings, clock)) as c:
        body = c.get("/api/signals/cabin_rh_ttl").json()
    [s] = body["signals"]
    assert s["id"] == "cabin_rh_ttl" and s["kind"] == "time_to_limit" and s["can_trigger"]


def test_signals_feature_off_is_404(settings, clock):
    with TestClient(app_with(settings, clock, frozenset({"serial"}))) as c:
        assert c.get("/api/signals").status_code == 404


def test_broken_signals_module_leaves_hub_starting(monkeypatch, settings, clock, caplog):
    monkeypatch.setitem(sys.modules, "hub.signals.routes", None)
    with caplog.at_level(logging.WARNING):
        app = app_with(settings, clock)
    with TestClient(app) as c:
        assert c.get("/api/status").status_code == 200
    assert "signals" in app.state.features.skipped and "signals" in caplog.text
```

Modify `hub/tests/test_config.py`:

```diff
--- a/hub/tests/test_config.py
+++ b/hub/tests/test_config.py
@@ -30,7 +30,7 @@
     assert s.http_host == "0.0.0.0"
     assert s.http_port == 8000
     assert s.cors_origins == ["*"]
-    assert s.features == {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food"}
+    assert s.features == {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food", "signals"}
     assert s.features == FEATURE_NAMES
     assert s.linksim_url == "http://127.0.0.1:8200"
     assert s.link_config == Path("linksim/link.json")
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_routes.py hub/tests/test_config.py
```

Expected (first error and summary):

```text
E           json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
1 failed, 1 warning in 0.40s
```

- [ ] **Step 3: Write the implementation**

Create `hub/signals/routes.py`:

```python
"""GET /api/signals and GET /api/signals/{id} (D45 §4.1). Read-only: nothing is stored."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from hub.contract import CREWS
from hub.signals.catalogue import BY_ID
from hub.signals.engine import evaluate
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import to_iso

router = APIRouter()


@dataclass
class SignalsState:
    store: Store
    rules: Sequence[Rule]
    crews: Sequence[str]
    tz: str
    clock: Callable[[], datetime]


def _reject(reason: str, status: int = 422) -> JSONResponse:
    return JSONResponse({"reason": reason}, status_code=status)


def _args(request: Request) -> tuple[SignalsState, list[str], datetime] | JSONResponse:
    st: SignalsState | None = getattr(request.app.state, "signals", None)
    if st is None:
        return _reject("signals_off", 503)
    crew = request.query_params.get("crew")
    if crew is not None and crew not in CREWS:
        return _reject("bad_crew")
    raw_at = request.query_params.get("at")
    if raw_at is None:
        at = st.clock()
    else:
        try:
            at = datetime.fromisoformat(raw_at)
        except ValueError:
            return _reject("bad_value:at")
        if at.tzinfo is None:
            return _reject("bad_value:at")
    return st, [crew] if crew else list(st.crews), at


@router.get("/api/signals")
def get_signals(request: Request) -> JSONResponse:
    a = _args(request)
    if isinstance(a, JSONResponse):
        return a
    st, crews, at = a
    sigs = evaluate(st.store, st.rules, crews=crews, at=at, tz=st.tz)
    crew = request.query_params.get("crew")
    return JSONResponse({"crew": crew, "at": to_iso(at), "signals": [s.to_dict() for s in sigs]})


@router.get("/api/signals/{sid}")
def get_signal(sid: str, request: Request) -> JSONResponse:
    if sid not in BY_ID:
        return _reject("unknown_signal", 404)
    a = _args(request)
    if isinstance(a, JSONResponse):
        return a
    st, crews, at = a
    sigs = evaluate(st.store, st.rules, crews=crews, at=at, tz=st.tz, ids=[sid])
    return JSONResponse({"at": to_iso(at), "signals": [s.to_dict() for s in sigs]})
```

Modify `hub/config.py`:

```diff
--- a/hub/config.py
+++ b/hub/config.py
@@ -8,7 +8,7 @@
 from pathlib import Path
 
 FEATURE_NAMES: frozenset[str] = frozenset(
-    {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food"}
+    {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food", "signals"}
 )
 KNOWN_CREWS: tuple[str, ...] = ("crew-a", "crew-b", "crew-c")
```

Modify `hub/features.py`:

```diff
--- a/hub/features.py
+++ b/hub/features.py
@@ -68,6 +68,10 @@
         "hub.food.log": ("FoodWriter",),
         "hub.food.routes": ("router",),
     },
+    "signals": {
+        "hub.signals.engine": ("evaluate",),
+        "hub.signals.routes": ("router", "SignalsState"),
+    },
 }
 
 
@@ -290,5 +294,15 @@
 
     if "food" in on and "food" not in f.skipped:
         _guard(f, "food", build_food, level=logging.ERROR)
+
+    def build_signals() -> None:
+        routes = f.mod("hub.signals.routes")
+        app.state.signals = routes.SignalsState(
+            ctx.store, ctx.assessor.rules, crews, settings.tz, ctx.clock
+        )
+        app.include_router(routes.router)
 
+    if "signals" in on and "signals" not in f.skipped:
+        _guard(f, "signals", build_signals)
+
     return rt
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_routes.py hub/tests/test_config.py
```

Expected:

```text
16 passed, 1 warning
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/config.py hub/features.py hub/signals/routes.py hub/tests/signals/test_routes.py hub/tests/test_config.py
git commit -m "feat(signals): GET /api/signals behind the signals feature"
```

### Task 4: The 28-day synthetic replay

A deterministic, labelled 28-day replay with planted effects, and a test that runs every slice-2 signal on it. `hub.sim.load_replay` learns to skip a `note` header line.

**Files:**
- Create: `hub/sim/signals_synth.py`
- Create: `hub/tests/signals/test_replay_signals.py`
- Create: `data/replay/signals-synthetic-28d.jsonl`
- Modify: `hub/sim/__init__.py`

**Interfaces:**
- Consumes: `hub.sim.ReplayLine`, `hub.contract.INDICATORS`; Task 2's `evaluate`.
- Produces: `hub/sim/signals_synth.py` with `synth(seed=45) -> list[ReplayLine]`, `write(path, lines)`, `earth_temp(t_ms)`, `NOTE`, `DAYS`, `END_MS`; `python -m hub.sim.signals_synth --out <file>`; `data/replay/signals-synthetic-28d.jsonl`.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/signals/test_replay_signals.py`:

```python
"""Every catalogue signal on the 28-day synthetic replay (D45 §9.2, §10)."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from hub.signals.engine import evaluate
from hub.sim import load_replay
from hub.sim.signals_synth import synth, write
from hub.tests.helpers import Rig, T

TZ = "America/Sao_Paulo"
REPO = Path(__file__).resolve().parents[3]
REAL_RULES = REPO / "data" / "thresholds.json"
END = T.replace(hour=10)  # the last line lands at 07:00 local


@pytest.fixture(scope="module")
def signals(tmp_path_factory):
    from hub.tests.conftest import FakeClock

    clock = FakeClock(END)
    rig = Rig(tmp_path_factory.mktemp("replay"), clock, rule_files=(REAL_RULES,))
    lines = synth()
    last = lines[-1].t_ms
    for i, ln in enumerate(lines, 1):
        msg = {**ln.msg, "node": "sim-1", "boot": 1, "seq": i, "age_ms": last - ln.t_ms,
               "src": "replay"}  # fmt: skip
        assert rig.ing.ingest_reading(msg, channel="test").reason is None
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a", "crew-b", "crew-c"],
                   at=END + timedelta(minutes=1), tz=TZ)  # fmt: skip
    return {(s.id, s.crew): s for s in out}


def test_every_replay_signal_is_marked_replay(signals):
    for s in signals.values():
        if s.state != "not_enough_data" or s.inputs:
            assert s.replay and all(i.src == "replay" for i in s.inputs), s.id


def test_crew_b_gets_nothing_from_the_replay(signals):
    assert all(s.state == "not_enough_data" and not s.inputs
               for (i, c), s in signals.items() if c == "crew-b")  # fmt: skip


def test_planted_rest_hr_rise_is_notable_and_flat_crew_is_steady(signals):
    a = signals[("rest_hr_baseline", "crew-a")]
    assert a.state == "notable" and a.headline_key == "signals.baseline.above"
    assert signals[("rest_hr_baseline", "crew-c")].state == "steady"


def test_rh_ramp_reaches_75_in_about_4_hours_not_yet_notable(signals):
    s = signals[("cabin_rh_ttl", None)]
    assert s.headline_key == "signals.ttl.reaches" and s.reference["limit"] == 75
    assert 3.0 <= s.value.low <= s.value.high <= 5.0 and s.state == "steady"
    assert signals[("cabin_rh_6h", None)].headline_key == "signals.trend.up"


def test_steady_and_gapped_series(signals):
    co2 = signals[("cabin_ppco2_ttl", None)]  # flat 1-hour mean far under 3 mmHg
    assert co2.state == "steady" and co2.headline_key in ("signals.ttl.none", "signals.ttl.away")
    assert signals[("spo2_baseline", "crew-c")].state == "not_enough_data"
    assert signals[("sleep_baseline", "crew-a")].state in ("steady", "notable")


def test_committed_replay_matches_the_generator(tmp_path):
    committed = REPO / "data" / "replay" / "signals-synthetic-28d.jsonl"
    fresh = tmp_path / "fresh.jsonl"
    write(fresh, synth())
    assert committed.read_bytes() == fresh.read_bytes()
    assert json.loads(committed.read_text().splitlines()[0])["kind"] == "note"
    assert len(load_replay(committed)) == len(synth())
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_replay_signals.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'hub.sim.signals_synth'
1 error in 0.11s
```

- [ ] **Step 3: Write the implementation**

Pressure lines sort before CO2 lines at the same time: the hub derives ppCO2 from a pressure within 60 s, and a CO2 sample that arrives first is flagged `assumed_pressure` and is not assessable. The replay test caught this.

Create `hub/sim/signals_synth.py`:

```python
"""28 invented days for the signals module (D45 §9.2): demo and test input, not measurements.

python -m hub.sim.signals_synth --out data/replay/signals-synthetic-28d.jsonl

Crews crew-a and crew-c only (never crew-b, the team owner's real ring data). Replay it with
`python -m hub.sim --file data/replay/signals-synthetic-28d.jsonl --backdate --http <hub>`: the last
line lands at "now" and every reading is node sim-1, src replay. Planted effects:
- crew-a resting HR about 9 bpm above its usual range on the last 3 nights;
- cabin RH ramping 3 %/h over the last 3 hours, about 3.8 h short of the 75 % limit at the end;
- crew-c resting HR flat; crew-c SpO2 on 4 nights only (gaps);
- crew-a water logged rising, crew-a body mass slowly falling;
- one space-weather day at level 1; the bench cabin temperature follows a daily cycle.
Camera sets are not in the file: hub.sim cannot create sessions, so lift signals show
`not enough data` on this replay (the engine tests cover them with direct sessions).
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from hub.contract import INDICATORS
from hub.sim import ReplayLine

DAYS = 28
H_MS = 3_600_000
DAY_MS = 24 * H_MS
END_MS = DAYS * DAY_MS  # the last line; nights end here, k days before it
CREWS = ("crew-a", "crew-c")
DEV = {
    "hr": "RING", "spo2": "RING", "sleep_h": "RING", "body_mass": "manual",
    "intake_water_ml": "catalog", "cabin_temp": "DHT22", "cabin_rh": "DHT22",
    "cabin_co2": "SCD41", "cabin_p": "BME280", "space_weather": "DONKI",
}  # fmt: skip
NOTE = {"t_ms": -1, "kind": "note", "note": "synthetic: invented data for the D45 signals demo"}


def _line(t_ms: int, ind: str, val: float, crew: str | None) -> ReplayLine:
    msg = {
        "v": 1, "node": "sim-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": ind,
        "val": round(val, 2), "unit": INDICATORS[ind], "src": "replay", "dev": DEV[ind],
        "q": ["ok"],
    }  # fmt: skip
    if crew is not None:
        msg["crew"] = crew
    return ReplayLine(int(t_ms), "reading", msg)


def earth_temp(t_ms: int) -> float:
    """A daily cycle peaking 15:00 local, where the last line is 07:00 local."""
    local_h = (7 + t_ms / H_MS) % 24
    return 18 + 6 * math.sin(2 * math.pi * (local_h - 9) / 24)


def synth(seed: int = 45) -> list[ReplayLine]:
    rnd = random.Random(seed)
    out: list[ReplayLine] = []
    for k in range(DAYS):
        night_end = END_MS - k * DAY_MS
        for crew in CREWS:
            a = crew == "crew-a"
            sleep_h = (7.0 if a else 7.5) + rnd.uniform(-0.4, 0.4)
            start = night_end - int(sleep_h * H_MS)
            base = 56 if a else 60
            rise = 9 if a and k < 3 else 0
            for t in range(start + 150_000, night_end, 300_000):  # one sample per 5 minutes
                out.append(_line(t, "hr", base + rise + rnd.uniform(-1.5, 1.5), crew))
            out.append(_line(night_end, "sleep_h", sleep_h, crew))
            if a or k in (0, 3, 9, 20):
                out.append(_line(night_end, "spo2", 97 + rnd.uniform(-0.5, 0.5), crew))
            if a or k % 3 == 0:
                lunch, dinner = night_end - 19 * H_MS, night_end - (12 - (k % 4)) * H_MS
                water = 400 + 20 * (DAYS - 1 - k) if a else 500
                out.append(_line(lunch, "intake_water_ml", 600 + rnd.uniform(-50, 50), crew))
                out.append(_line(dinner, "intake_water_ml", water + rnd.uniform(-50, 50), crew))
            if a:
                mass = 72.0 - 0.02 * (DAYS - 1 - k) + rnd.uniform(-0.1, 0.1)
                out.append(_line(night_end + 1_800_000, "body_mass", mass, crew))
        if k > 0:
            out.append(_line(night_end + 2 * H_MS, "space_weather", 1 if k == 5 else 0, None))
    for t in range(END_MS - 7 * DAY_MS, END_MS + 1, 300_000):
        if t < END_MS - 2 * DAY_MS and (t // 300_000) % 6:
            continue  # every 30 minutes before the last 2 days, every 5 minutes after
        temp = 22 + 0.3 * (earth_temp(t - 2 * H_MS) - 18) + rnd.uniform(-0.1, 0.1)
        ramp_h = (t - (END_MS - 3 * H_MS)) / H_MS
        rh = 54.5 + 3 * ramp_h if ramp_h > 0 else 45 + rnd.uniform(-1, 1)
        out.append(_line(t, "cabin_temp", temp, None))
        out.append(_line(t, "cabin_rh", rh, None))
        if t >= END_MS - 2 * DAY_MS:
            out.append(_line(t, "cabin_co2", 900 + rnd.uniform(-20, 20), None))
            out.append(_line(t, "cabin_p", 1013 + rnd.uniform(-1, 1), None))
    # cabin_p before cabin_co2 at the same time: the hub derives ppCO2 from the pressure within
    # 60 s, and a CO2 sample that arrives first is flagged assumed_pressure (not assessable).
    out.sort(
        key=lambda x: (x.t_ms, x.msg["ind"] != "cabin_p", x.msg["ind"], x.msg.get("crew") or "")
    )
    return out


def write(path: Path, lines: list[ReplayLine]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        f.write(json.dumps(NOTE, separators=(",", ":")) + "\n")
        f.writelines(json.dumps({"t_ms": ln.t_ms, "kind": ln.kind, "msg": ln.msg},
                               separators=(",", ":")) + "\n" for ln in lines)  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    write(ap.parse_args().out, synth())


if __name__ == "__main__":
    main()
```

Generate `data/replay/signals-synthetic-28d.jsonl` (do not hand-write it):

```bash
python -m hub.sim.signals_synth --out data/replay/signals-synthetic-28d.jsonl
```

Modify `hub/sim/__init__.py`:

```diff
--- a/hub/sim/__init__.py
+++ b/hub/sim/__init__.py
@@ -29,6 +29,8 @@
         if not raw:
             continue
         d = json.loads(raw)
+        if d.get("kind") not in ("reading", "rep"):
+            continue  # a header such as {"kind": "note", ...} says what the file is
         lines.append(ReplayLine(int(d["t_ms"]), d["kind"], d["msg"]))
     return lines
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_replay_signals.py
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add data/replay/signals-synthetic-28d.jsonl hub/sim/__init__.py hub/sim/signals_synth.py hub/tests/signals/test_replay_signals.py
git commit -m "feat(signals): 28-day synthetic replay for the signals demo"
```

To watch it on a local hub (a scratch DB, never the live hub's):

```bash
HUB_DB=var/scratch-signals.db HUB_HTTP_PORT=8010 python -m hub &
python -m hub.sim --file data/replay/signals-synthetic-28d.jsonl --backdate --http http://127.0.0.1:8010
curl -s 'http://127.0.0.1:8010/api/signals?crew=crew-a' | python -m json.tool | head -40
```

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat(signals): D45 engine, API and replay" --body "Implements D45 slice 2 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 2–4."
```

---

## Slice 3: reference feeds, ISS storage and the weather importer (PR 3)

Branch `feat/d45-reference-feeds`. The ISS units and the provider (INMET) were decided on 2026-11-15
(spec §13). Tasks 6–8 can start at once; Task 9 waits for the team owner's INMET token.

### Task 5: Decided: ISS units and the weather provider (record only)

Decided on 2026-11-15; nothing to build. Record it in the slice-3 PR description.

- [ ] **Step 1: Copy these decisions into the slice-3 PR description**:
  - ISS units confirmed: pressure mmHg → stored hPa (×1.333224), temperature C, both ppCO2 items mmHg. The capture
    `data/nasa/isslive_capture.jsonl` reads 758.6, 23.3–23.8, 2.44 and 2.95.
  - `iss_ppco2_6h` uses 30-minute blocks (decision 13); already in Task 6's catalogue.
  - Outdoor provider: INMET automatic stations (decision 14). The card text stays vendor-free ("Earth reference,
    outdoor"); INMET is named in `DATA_SOURCES.md` only.
- [ ] **Step 2: The team owner requests the INMET token.** This is the team owner's own action (an e-mail from their
  own address to INMET's registration desk, `cadastro.act@inmet.gov.br`, per the INMET.jl README; no official
  manual page was found on 2026-11-15). The token goes into `.env` as `INMET_TOKEN` and is never committed, logged or
  pasted into chat. Task 9 waits for it; Tasks 6–8 do not.

### Task 6: Contract: reference feeds, quiet and off /api/status

The contract learns the six reference indicators, node `earth-1`, src `ref` and devs `ISSLIVE` and `WEATHER`. They are quiet: stored, but never assessed, outboxed, pushed or listed on `/api/status`. The catalogue gains `iss_ppco2_6h`. A small test kit (`kit.py`) is shared by the signals tests from here on.

**Files:**
- Create: `hub/tests/signals/kit.py`
- Create: `hub/tests/signals/test_reference_feeds.py`
- Modify: `hub/signals/catalogue.py`
- Modify: `hub/contract.py`
- Modify: `hub/ingest.py`
- Modify: `hub/assess.py`

**Interfaces:**
- Consumes: Task 2's engine (`iss_ppco2_6h` uses the existing `("trend", "cabin")` builder).
- Produces: `hub.contract.REFERENCE_INDS`; `hub.ingest.QUIET_INDS` now includes it; `hub.assess.status_body` skips it; `hub/tests/signals/kit.py` with `real_rig`, `one`, `put_ref`, `meal`, `night`, `lift_set`, `END`, `TZ`.

- [ ] **Step 1: Write the failing tests**

Create `hub/tests/signals/kit.py`:

```python
"""Builders shared by the signals tests: a rig with the real thresholds and one-line inputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from hub.contract import INDICATORS
from hub.signals.engine import evaluate
from hub.signals.types import Signal
from hub.tests.helpers import Rig, T

TZ = "America/Sao_Paulo"
REAL_RULES = Path(__file__).resolve().parents[3] / "data" / "thresholds.json"
END = T.replace(hour=10)  # 07:00 local


def real_rig(tmp_path, clock) -> Rig:
    return Rig(tmp_path, clock, rule_files=(REAL_RULES,))


def one(
    rig: Rig, sid: str, crew: str | None = "crew-a", at: datetime = END + timedelta(hours=1)
) -> Signal:
    [s] = evaluate(rig.store, rig.assessor.rules, crews=[crew] if crew else [], at=at, tz=TZ,
                   ids=[sid])  # fmt: skip
    return s


def put_ref(
    rig: Rig, ind: str, val: float, at: datetime, *, node: str, dev: str, src: str,
    crew: str | None = None,
) -> None:  # fmt: skip
    """A reading Rig.put cannot build (no default device for the indicator)."""
    rig.clock.set(at)
    rig.seq += 1
    m = {"v": 1, "node": node, "boot": 1, "seq": rig.seq, "age_ms": 0, "ind": ind, "val": val,
         "unit": INDICATORS[ind], "src": src, "dev": dev, "q": ["ok"]}  # fmt: skip
    if crew is not None:
        m["crew"] = crew
    res = rig.ing.ingest_reading(m, channel="test")
    assert res.reason is None, res.reason


def meal(rig: Rig, at: datetime, water: float, crew: str = "crew-a") -> None:
    rig.put("intake_water_ml", water, at, node="food", dev="catalog", src="self", crew=crew)


def night(rig: Rig, end: datetime, sleep_h: float, crew: str = "crew-a") -> None:
    rig.put("sleep_h", sleep_h, end, node="ring-1", dev="RING", crew=crew)


def lift_set(rig: Rig, sid: str, start: datetime, works: list[float], crew: str = "crew-a",
             exercise: str = "curl", node: str = "camera") -> None:  # fmt: skip
    """One camera set: a session row and one camera rep per work value (joules at Earth g)."""
    rig.store.insert_session(sid, 5.0, 9.81, crew, start, exercise)
    for i, w in enumerate(works, 1):
        rig.clock.set(start + timedelta(seconds=5 * i))
        rep = {
            "v": 1, "node": node, "boot": 1, "seq": rig.seq + i, "age_ms": 0, "type": "rep",
            "session": sid, "rep": i, "src": "camera", "peak_n": 60.0, "work_j": w,
            "rom_m": 0.4, "g": 9.81, "mass_kg": 5.0, "t0_ms": 0, "t1_ms": 1500,
            "exercise": exercise,
        }  # fmt: skip
        assert rig.ing.ingest_rep(rep, channel="test").reason is None
    rig.seq += len(works)
```

Create `hub/tests/signals/test_reference_feeds.py`:

```python
"""Reference feeds (D45 §4.2): stored, quiet, off /api/status, and usable by the signals."""

from datetime import timedelta

import pytest

from hub.assess import status_body
from hub.contract import REFERENCE_INDS, parse_reading
from hub.tests.helpers import T
from hub.tests.signals.kit import one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_contract_accepts_the_new_feeds():
    for ind, unit in (("earth_temp", "C"), ("earth_rh", "%"), ("earth_p", "hPa")):
        parse_reading({"v": 1, "node": "earth-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": ind,
                       "val": 20, "unit": unit, "src": "ref", "dev": "WEATHER", "q": ["ok"]})  # fmt: skip
    assert REFERENCE_INDS == {
        "iss_cabin_p", "iss_cabin_temp", "iss_ppco2", "earth_temp", "earth_rh", "earth_p",
    }  # fmt: skip


def test_reference_feeds_are_quiet_and_off_status(rig):
    put_ref(rig, "earth_temp", 15.0, T, node="earth-1", dev="WEATHER", src="ref")
    assert rig.store.count("readings") == 1
    assert rig.store.count("outbox") == 0 and rig.store.count("assessments") == 0
    assert rig.events == []
    body = status_body(rig.store, [], None, T)
    assert all(r["ind"] not in REFERENCE_INDS for r in body["results"])


def test_iss_ppco2_trend_uses_the_cabin_builder(rig):
    for i in range(6 * 60):
        put_ref(rig, "iss_ppco2", 2.0 + 0.1 * i / 60, T - timedelta(minutes=6 * 60 - 1 - i),
                node="nasa", dev="ISSLIVE", src="nasa")  # fmt: skip
    s = one(rig, "iss_ppco2_6h", crew=None, at=T)
    assert s.headline_key == "signals.trend.up" and s.value.unit == "mmHg" and s.crew is None
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_reference_feeds.py
```

Expected (first error and summary):

```text
E   ImportError: cannot import name 'REFERENCE_INDS' from 'hub.contract' (hub/contract.py)
1 error in 0.09s
```

- [ ] **Step 3: Write the implementation**

Modify `hub/signals/catalogue.py`:

```diff
--- a/hub/signals/catalogue.py
+++ b/hub/signals/catalogue.py
@@ -64,6 +64,10 @@
          can_trigger=True, limits=(RING,)),
     Spec("spo2_baseline", "baseline", "night_value", "spo2", 14 * D, None, 7, 0.0, True,
          can_trigger=True, side="low", limits=(RING,)),
+    # slice 3: ISS Live stored as readings
+    # 30-minute blocks: ISS Live pushes a value only when it changes (team owner, 2026-11-15).
+    Spec("iss_ppco2_6h", "trend", "cabin", "iss_ppco2", 6 * H, 30 * MIN, 10, 0.75, False,
+         limits=(INDEPENDENCE, ISS)),
 )  # fmt: skip
 
 BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
```

Modify `hub/contract.py`:

```diff
--- a/hub/contract.py
+++ b/hub/contract.py
@@ -39,7 +39,17 @@
     "intake_iron_mg": "mg",
     "intake_vitd_ug": "ug",
     "body_mass": "kg",
+    # Reference feeds (D45 §4.2): stored for signals, never assessed, outboxed or on /api/status.
+    "iss_cabin_p": "hPa",
+    "iss_cabin_temp": "C",
+    "iss_ppco2": "mmHg",
+    "earth_temp": "C",
+    "earth_rh": "%",
+    "earth_p": "hPa",
 }
+REFERENCE_INDS: frozenset[str] = frozenset(
+    {"iss_cabin_p", "iss_cabin_temp", "iss_ppco2", "earth_temp", "earth_rh", "earth_p"}
+)
 DERIVED: dict[str, str] = {"cabin_ppco2": "mmHg"}
 
 CABIN_INDS: frozenset[str] = frozenset(
@@ -81,14 +91,14 @@
 
 NODES: frozenset[str] = frozenset(
     {"vitals-1", "cabin-1", "exercise-1", "strap-1", "manual", "camera", "sim-1", "nasa", "food",
-     "tilt-1", "ring-1"}
+     "tilt-1", "ring-1", "earth-1"}
 )
-SOURCES: frozenset[str] = frozenset({"certified", "hobby", "self", "nasa", "replay"})
+SOURCES: frozenset[str] = frozenset({"certified", "hobby", "self", "nasa", "replay", "ref"})
 DEVICES: frozenset[str] = frozenset(
     {
         "MAX30102", "DS18B20", "MLX90614", "SCD41", "BME280", "DHT22", "DHT11", "BH1750",
         "HX711", "H10", "manual", "camera", "MPU6050", "MH-Z19", "DONKI", "OSDR", "catalog",
-        "NTC", "KY039", "KY017", "RING",
+        "NTC", "KY039", "KY017", "RING", "ISSLIVE", "WEATHER",
     }
 )  # fmt: skip
 FLAGS: frozenset[str] = frozenset(
```

Modify `hub/ingest.py`:

```diff
--- a/hub/ingest.py
+++ b/hub/ingest.py
@@ -11,6 +11,7 @@
 from hub.contract import (
     BODY_INDS,
     INTAKE_INDS,
+    REFERENCE_INDS,
     ContractError,
     Reading,
     parse_reading,
@@ -27,7 +28,7 @@
 
 CREW_SCOPED = BODY_INDS | INTAKE_INDS
 # Streams that are stored but never assessed, outboxed or pushed one by one.
-QUIET_INDS = frozenset({"load_raw"})
+QUIET_INDS = frozenset({"load_raw"}) | REFERENCE_INDS
 # Channels fed by hardware nodes, whose (node, boot, seq) key can repeat when a boot counter does
 # (tilt-1, bench 2026-11-15). A repeated key with a different sample is stored under a `clash`
 # number there; software producers (http, prompt, internal) keep exact idempotency.
```

Modify `hub/assess.py`:

```diff
--- a/hub/assess.py
+++ b/hub/assess.py
@@ -9,7 +9,7 @@
 from pathlib import Path
 from zoneinfo import ZoneInfo
 
-from hub.contract import BODY_INDS, DERIVED, INDICATORS, INTAKE_INDS
+from hub.contract import BODY_INDS, DERIVED, INDICATORS, INTAKE_INDS, REFERENCE_INDS
 from hub.results import Alert, AssessmentResult, entry_for, escalate_to_for
 from hub.store import Store, StoredReading
 from hub.thresholds import Rule, band_status, rules_for
@@ -258,6 +258,8 @@
     """GET /api/status body (D2): one worst-of entry per indicator that has any reading."""
     results = []
     for ind in [*INDICATORS, *DERIVED]:
+        if ind in REFERENCE_INDS:
+            continue
         scoped = crew is not None and ind in CREW_SCOPED
         r = store.latest_reading(ind, crew=crew, scope_crew=scoped)
         if r is None:
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_reference_feeds.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/assess.py hub/contract.py hub/ingest.py hub/signals/catalogue.py hub/tests/signals/kit.py hub/tests/signals/test_reference_feeds.py
git commit -m "feat(contract): quiet reference feeds (ISS and Earth) for D45 signals"
```

### Task 7: ISS Live items stored as readings

Each fresh ISS Live item update becomes one internal reading, at most one per item per minute. Units come from the table the ISS route already serves, confirmed by the team owner (decision 3).

**Files:**
- Create: `hub/nasa/iss_store.py`
- Create: `hub/tests/test_iss_store.py`
- Modify: `hub/features.py`
- Modify: `DATA_SOURCES.md`

**Interfaces:**
- Consumes: `IssLiveClient(on_update=...)`, `IssItemUpdate`, `ISS_ITEMS`, `isslive_routes.UNITS` and `MMHG_TO_HPA`; `Ingestor.ingest_internal`; Task 6's indicators.
- Produces: `hub/nasa/iss_store.py` with `IssWriter(ingest, *, boot).on_update(u) -> bool`, `to_hub_unit(name, val)`, `IND_FOR`, `MIN_GAP = 1 min`, `FRESH = 10 min`; `build_iss` passes `on_update=writer.on_update`.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/test_iss_store.py`:

```python
from datetime import timedelta

import pytest

from hub.nasa.iss_store import IssWriter, to_hub_unit
from hub.nasa.isslive import IssItemUpdate
from hub.tests.helpers import Rig, T


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


def upd(item, val, at, received=None):
    return IssItemUpdate(item, val, 0.0, at, None, received or at + timedelta(seconds=2))


def send(rig, w, u):
    """Deliver an update as the client does: the hub clock reads the update's arrival time."""
    rig.clock.set(u.received_at)
    return w.on_update(u)


def test_pressure_is_stored_in_hpa_and_quiet(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert send(rig, w, upd("USLAB000058", 760.0, T))
    [r] = rig.store.readings("iss_cabin_p")
    assert r.val == pytest.approx(1013.25, abs=0.01) and r.unit == "hPa"
    assert (r.node, r.src, r.dev, r.crew) == ("nasa", "nasa", "ISSLIVE", None)
    assert rig.store.count("outbox") == 0 and rig.store.count("assessments") == 0


def test_one_row_per_item_per_minute(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert send(rig, w, upd("USLAB000055", 2.1, T))
    assert not send(rig, w, upd("USLAB000055", 2.2, T + timedelta(seconds=30)))
    assert send(rig, w, upd("NODE3000003", 2.4, T + timedelta(seconds=30)))  # another item
    assert send(rig, w, upd("USLAB000055", 2.3, T + timedelta(seconds=61)))
    assert [r.val for r in rig.store.readings("iss_ppco2")] == [2.1, 2.4, 2.3]


def test_stale_and_unknown_items_are_skipped(rig):
    w = IssWriter(rig.ing.ingest_internal, boot=1)
    assert not send(rig, w, upd("USLAB000059", 21.0, T, received=T + timedelta(minutes=11)))
    assert not send(rig, w, upd("TIME_000001", 1.0, T))
    assert rig.store.count("readings") == 0


def test_temperature_and_ppco2_keep_their_units():
    assert to_hub_unit("cabin_temperature", 21.5) == 21.5
    assert to_hub_unit("lab_ppco2", 2.7) == 2.7
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/test_iss_store.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'hub.nasa.iss_store'
1 error in 0.08s
```

- [ ] **Step 3: Write the implementation**

Create `hub/nasa/iss_store.py`:

```python
"""ISS Live items stored as reference readings (D45 §4.2). Units come from isslive_routes.UNITS,
the table the ISS cabin route already serves, so the stored values match what the console shows."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from hub.contract import INDICATORS, Reading
from hub.nasa.isslive import ISS_ITEMS, IssItemUpdate
from hub.nasa.isslive_routes import MMHG_TO_HPA, UNITS

log = logging.getLogger("hub.nasa.iss_store")

NODE = "nasa"
DEV = "ISSLIVE"
MIN_GAP = timedelta(minutes=1)  # at most one row per item per minute
FRESH = timedelta(minutes=10)  # an item older than this when it arrives is not stored
# ISS item name -> hub indicator. Both ppCO2 items are stored as iss_ppco2 (lab and Node 3).
IND_FOR: dict[str, str] = {
    "cabin_pressure": "iss_cabin_p",
    "cabin_temperature": "iss_cabin_temp",
    "lab_ppco2": "iss_ppco2",
    "node3_ppco2": "iss_ppco2",
}


def to_hub_unit(name: str, val: float) -> float:
    """The ISS value in the hub indicator's unit: pressure mmHg -> hPa; the others unchanged."""
    if IND_FOR[name] == "iss_cabin_p" and UNITS[name] == "mmHg":
        return round(val * MMHG_TO_HPA, 2)
    return val


class IssWriter:
    """IssLiveClient's on_update callback: one internal reading per fresh item update."""

    def __init__(self, ingest: Callable[[Reading], object], *, boot: int) -> None:
        self.ingest = ingest
        self.boot = boot
        self._seq = 0
        self._last: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def on_update(self, u: IssItemUpdate) -> bool:
        """True when a reading was handed to the ingestor."""
        name = ISS_ITEMS.get(u.item)
        if name not in IND_FOR:
            return False
        if u.received_at - u.measured_at > FRESH:
            return False
        with self._lock:
            last = self._last.get(u.item)
            if last is not None and u.measured_at - last < MIN_GAP:
                return False
            self._last[u.item] = u.measured_at
            self._seq += 1
            seq = self._seq
        age_ms = max(0, int((u.received_at - u.measured_at).total_seconds() * 1000))
        ind = IND_FOR[name]
        r = Reading(
            v=1, node=NODE, boot=self.boot, seq=seq, age_ms=age_ms, ind=ind,
            val=to_hub_unit(name, u.val), unit=INDICATORS[ind], src="nasa", dev=DEV, q=("ok",),
            crew=None, code=None,
        )  # fmt: skip
        try:
            self.ingest(r)
        except Exception:
            log.exception("iss reading %s failed", ind)
            return False
        return True
```

Modify `hub/features.py`:

```diff
--- a/hub/features.py
+++ b/hub/features.py
@@ -60,6 +60,7 @@
     "iss": {
         "hub.nasa.isslive": ("IssLiveState", "ISS_ITEMS"),
         "hub.nasa.isslive_client": ("IssLiveClient",),
+        "hub.nasa.iss_store": ("IssWriter",),
     },
     "wearable": {"hub.wearable.routes": ("WearableState", "router")},
     "mcp": {"hub.mcp_server": ("build_mcp",)},
@@ -243,8 +244,11 @@
             raise RuntimeError("needs nasa")
         m = f.mod
         state = m("hub.nasa.isslive").IssLiveState()
+        writer = m("hub.nasa.iss_store").IssWriter(
+            ctx.ingestor.ingest_internal, boot=int(ctx.clock().timestamp())
+        )
         rt.iss_client = m("hub.nasa.isslive_client").IssLiveClient(
-            list(m("hub.nasa.isslive").ISS_ITEMS), state
+            list(m("hub.nasa.isslive").ISS_ITEMS), state, on_update=writer.on_update
         )
         rt.nasa.iss = state
```

Modify `DATA_SOURCES.md`:

```diff
--- a/DATA_SOURCES.md
+++ b/DATA_SOURCES.md
@@ -38,6 +38,9 @@
 - Committed file: `data/nasa/isslive_capture.jsonl`, a 13-minute capture (13:56 to 14:10 UTC) recorded on 2026-11-14, all four items present, always shown as "recorded".
 - Use: "ISS cabin now" beside the habitat cabin, with a data-age badge.
 - Without it: the page serves the recorded capture, labelled recorded.
+- Stored (D45): the hub also stores each fresh item as a reference reading (`iss_cabin_p` in hPa from the mmHg value,
+  `iss_cabin_temp` in C, `iss_ppco2` in mmHg for both CO2 items), at most one per item per minute. These readings are
+  never assessed, never sent over the link and never on `/api/status`; the signals module reads them.
 
 ## Mission dose estimate (effective dose)
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/test_iss_store.py
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add DATA_SOURCES.md hub/features.py hub/nasa/iss_store.py hub/tests/test_iss_store.py
git commit -m "feat(nasa): store ISS Live atmosphere items as quiet reference readings"
```

### Task 8: The outdoor weather importer (`nodes/weather`)

A separate process, like the ring importer: the hub never calls the internet. Everything except the provider adapter: pure mapper, coarse location, provider seam (refuses until Task 9), CLI, docs, and the replay's outdoor-temperature lines.

**Files:**
- Create: `nodes/weather/__init__.py`
- Create: `nodes/weather/mapper.py`
- Create: `nodes/weather/location.py`
- Create: `nodes/weather/provider.py`
- Create: `nodes/weather/__main__.py`
- Create: `nodes/weather/tests/__init__.py`
- Create: `nodes/weather/tests/test_weather.py`
- Modify: `hub/sim/signals_synth.py`
- Modify: `DATA_SOURCES.md`
- Modify: `.env.example`
- Modify: `data/replay/signals-synthetic-28d.jsonl`

**Interfaces:**
- Consumes: `nodes.ring.hubpost.post_readings`; Task 6's contract additions.
- Produces:
  - `nodes/weather/mapper.py`: `HourRow(t, temp_c, rh_pct, p_hpa)`, `map_hours(rows, *, now_ms) -> list[dict]` (node `earth-1`, src `ref`, dev `WEATHER`, fixed `seq` per hour and indicator).
  - `nodes/weather/location.py`: `coarse_location(env, dotenv) -> (lat, lon)` rounded to 1 decimal, `env_file_values(path)`, `LocationError`.
  - `nodes/weather/provider.py`: `Provider` protocol (`hours(start, end) -> list[HourRow]`), `NoProvider`, `default_provider(lat, lon)`.
  - `nodes/weather/__main__.py`: `run_pull(provider, *, hours, now, post) -> dict`, `main(argv)`; `python -m nodes.weather pull [--hours N] [--hub URL] [--dry-run]` prints counts only.

- [ ] **Step 1: Write the failing tests**

Create `nodes/weather/tests/__init__.py` (empty file).

Create `nodes/weather/tests/test_weather.py`:

```python
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
    assert coarse_location({"WEATHER_LAT": "-23.5617", "WEATHER_LON": "-46.6559"}, {}) == (
        -23.6,
        -46.7,
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
    values = [env[k] for k in ("WEATHER_LAT", "WEATHER_LON") if env.get(k)]
    if not values:
        pytest.skip("no local .env location to check")
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()  # fmt: skip
    for f in tracked:
        p = REPO / f
        if p.is_file() and p.stat().st_size < 2_000_000:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for v in values:
                assert v not in text, f"{f} holds the bench location"
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q nodes/weather/tests/test_weather.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'nodes.weather.__main__'
1 error in 0.06s
```

- [ ] **Step 3: Write the implementation**

Create `nodes/weather/__init__.py` (empty file).

Create `nodes/weather/mapper.py`:

```python
"""Hourly outdoor weather -> contract-v1 readings (D45 §4.2). Pure: no network, no clock, no files.

Node earth-1, src ref, dev WEATHER, no crew. A missing value is skipped, never filled. `seq` is
fixed per hour and indicator, so pulling the same hours twice is a harmless duplicate at the hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

NODE = "earth-1"
DEV = "WEATHER"
SRC = "ref"
BOOT = 1
K: dict[str, int] = {"earth_temp": 1, "earth_rh": 2, "earth_p": 3}
UNITS: dict[str, str] = {"earth_temp": "C", "earth_rh": "%", "earth_p": "hPa"}
RANGES: dict[str, tuple[float, float]] = {
    "earth_temp": (-90.0, 60.0), "earth_rh": (0.0, 100.0), "earth_p": (850.0, 1090.0),
}  # fmt: skip


@dataclass(frozen=True)
class HourRow:
    t: datetime  # aware, the hour the provider reports
    temp_c: float | None
    rh_pct: float | None
    p_hpa: float | None


def map_hours(rows: list[HourRow], *, now_ms: int) -> list[dict]:
    """Readings in time order; age_ms is the true age of each hour at `now_ms`."""
    out: list[tuple[int, int, dict]] = []
    for row in rows:
        t_ms = int(row.t.timestamp() * 1000)
        if t_ms > now_ms:
            continue  # a forecast hour is not a reading
        for ind, val in (
            ("earth_temp", row.temp_c),
            ("earth_rh", row.rh_pct),
            ("earth_p", row.p_hpa),
        ):
            if val is None:
                continue
            lo, hi = RANGES[ind]
            out.append((t_ms, K[ind], {
                "v": 1, "node": NODE, "boot": BOOT, "seq": t_ms // 3_600_000 * 4 + K[ind],
                "age_ms": now_ms - t_ms, "ind": ind, "val": float(val), "unit": UNITS[ind],
                "src": SRC, "dev": DEV, "q": ["ok"] if lo <= val <= hi else ["out_of_range"],
            }))  # fmt: skip
    out.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in out]
```

Create `nodes/weather/location.py`:

```python
"""The bench location as a coarse grid cell (D45 §4.2). Read from WEATHER_LAT / WEATHER_LON in the
environment or .env; rounded to 1 decimal (about 11 km) before any use; never logged or posted."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

DECIMALS = 1


class LocationError(ValueError):
    pass


def env_file_values(path: Path) -> dict[str, str]:
    """KEY=value lines of a .env file; a missing file gives {}."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def coarse_location(env: Mapping[str, str], dotenv: Mapping[str, str]) -> tuple[float, float]:
    """(lat, lon) rounded to DECIMALS. The environment wins over .env."""
    raw = {k: env.get(k) or dotenv.get(k) for k in ("WEATHER_LAT", "WEATHER_LON")}
    if not raw["WEATHER_LAT"] or not raw["WEATHER_LON"]:
        raise LocationError("set WEATHER_LAT and WEATHER_LON (in .env, never committed)")
    try:
        lat, lon = float(raw["WEATHER_LAT"]), float(raw["WEATHER_LON"])
    except ValueError:
        raise LocationError("WEATHER_LAT and WEATHER_LON must be numbers") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LocationError("WEATHER_LAT or WEATHER_LON is out of range")
    return round(lat, DECIMALS), round(lon, DECIMALS)
```

Create `nodes/weather/provider.py`:

```python
"""The weather provider seam (D45 §4.2). The provider itself is the team owner's choice (spec §13);
until it is chosen, default_provider refuses to run, so nothing is fetched by accident."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nodes.weather.mapper import HourRow


class Provider(Protocol):
    def hours(self, start: datetime, end: datetime) -> list[HourRow]:
        """Observed hourly rows in [start, end], oldest first; missing values are None."""
        ...


class NoProvider:
    def hours(self, start: datetime, end: datetime) -> list[HourRow]:
        raise RuntimeError("no weather provider chosen yet (D45 §13); see DATA_SOURCES.md")


def default_provider(lat: float, lon: float) -> Provider:
    return NoProvider()
```

Create `nodes/weather/__main__.py`:

```python
"""python -m nodes.weather pull [--hours N] [--hub URL] [--dry-run]: outdoor Earth reference (D45).

A separate process, like the ring importer: the habitat hub never calls the internet. Each run
fetches the last N hours for the coarse bench cell and posts them as earth-1 readings (src ref).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from nodes.ring.hubpost import post_readings
from nodes.weather.location import LocationError, coarse_location, env_file_values
from nodes.weather.mapper import map_hours
from nodes.weather.provider import Provider, default_provider

DEFAULT_HUB = "http://127.0.0.1:8000"
log = logging.getLogger("nodes.weather")


def run_pull(
    provider: Provider, *, hours: int, now: datetime, post: Callable[[list[dict]], dict] | None,
) -> dict:  # fmt: skip
    rows = provider.hours(now - timedelta(hours=hours), now)
    readings = map_hours(rows, now_ms=int(now.timestamp() * 1000))
    counts = {"hours": len(rows), "readings": len(readings)}
    if post is not None:
        counts.update(post(readings))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nodes.weather")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull", help="fetch the last N hours and post them to the hub")
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--hub", default=os.environ.get("WEATHER_HUB", DEFAULT_HUB))
    p.add_argument("--dry-run", action="store_true", help="fetch and map, post nothing")
    a = ap.parse_args(argv)
    try:
        lat, lon = coarse_location(os.environ, env_file_values(Path(".env")))
    except LocationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    provider = default_provider(lat, lon)
    now = datetime.now(UTC)
    if a.dry_run:
        counts = run_pull(provider, hours=a.hours, now=now, post=None)
    else:
        with httpx.Client(base_url=a.hub, timeout=10) as http:
            counts = run_pull(provider, hours=a.hours, now=now,
                              post=lambda rs: post_readings(rs, http))  # fmt: skip
    print(" ".join(f"{k}={v}" for k, v in counts.items()))  # counts only: never the location
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Modify `hub/sim/signals_synth.py`:

```diff
--- a/hub/sim/signals_synth.py
+++ b/hub/sim/signals_synth.py
@@ -9,7 +9,8 @@
 - cabin RH ramping 3 %/h over the last 3 hours, about 3.8 h short of the 75 % limit at the end;
 - crew-c resting HR flat; crew-c SpO2 on 4 nights only (gaps);
 - crew-a water logged rising, crew-a body mass slowly falling;
-- one space-weather day at level 1; the bench cabin temperature follows a daily cycle.
+- one space-weather day at level 1; outdoor Earth temperature with a daily cycle the bench
+  cabin follows about 2 hours later.
 Camera sets are not in the file: hub.sim cannot create sessions, so lift signals show
 `not enough data` on this replay (the engine tests cover them with direct sessions).
 """
@@ -33,7 +34,7 @@
 DEV = {
     "hr": "RING", "spo2": "RING", "sleep_h": "RING", "body_mass": "manual",
     "intake_water_ml": "catalog", "cabin_temp": "DHT22", "cabin_rh": "DHT22",
-    "cabin_co2": "SCD41", "cabin_p": "BME280", "space_weather": "DONKI",
+    "cabin_co2": "SCD41", "cabin_p": "BME280", "earth_temp": "WEATHER", "space_weather": "DONKI",
 }  # fmt: skip
 NOTE = {"t_ms": -1, "kind": "note", "note": "synthetic: invented data for the D45 signals demo"}
 
@@ -81,6 +82,8 @@
                 out.append(_line(night_end + 1_800_000, "body_mass", mass, crew))
         if k > 0:
             out.append(_line(night_end + 2 * H_MS, "space_weather", 1 if k == 5 else 0, None))
+    for t in range(END_MS - 7 * DAY_MS, END_MS + 1, H_MS):
+        out.append(_line(t, "earth_temp", earth_temp(t) + rnd.uniform(-0.2, 0.2), None))
     for t in range(END_MS - 7 * DAY_MS, END_MS + 1, 300_000):
         if t < END_MS - 2 * DAY_MS and (t // 300_000) % 6:
             continue  # every 30 minutes before the last 2 days, every 5 minutes after
```

Modify `DATA_SOURCES.md`:

```diff
--- a/DATA_SOURCES.md
+++ b/DATA_SOURCES.md
@@ -100,3 +100,17 @@
 - Committed file: `data/replay/ring-synthetic-nights.jsonl`, a **synthetic** pull (invented values in the vendor's field layout, labelled so on its first line). Real pulls are saved to `var/ring/pulls.jsonl` (mode 600, git-ignored) and are never committed.
 - Use: delayed cloud sync of vitals. A pull is `src hobby` with its true age; a replay is `src replay`, shown as "Replay (recorded)". The habitat core never calls the cloud; the importer is a separate process that posts to `POST /api/readings`.
 - Without it: the vitals tiles stay empty; the synthetic replay keeps the demo working with no network.
+
+## Earth weather (outdoor reference, D45)
+
+- Use: the outdoor temperature, humidity and pressure next to the bench cabin, for the signals module's
+  "side by side" card. Readings are node `earth-1`, `src ref`, device `WEATHER`, shown as "Earth reference, outdoor".
+- Importer: `python -m nodes.weather pull --hours 48`, a separate process like the ring importer. The habitat hub
+  never calls the internet.
+- Location: a coarse grid cell (1 decimal, about 11 km) from `WEATHER_LAT` and `WEATHER_LON` in `.env`
+  (git-ignored), used only to pick the nearest station. The cell and the station code are never committed, posted,
+  logged or shown.
+- Provider: INMET (Instituto Nacional de Meteorologia) automatic stations, chosen by the team owner on 2026-11-15.
+  Endpoint, token, fields, terms and access date go here when the adapter lands (D45 plan, Task 9). Until then
+  `nodes/weather` refuses to fetch.
+- Without it: the "side by side" card says not enough data; nothing else changes.
```

Modify `.env.example`:

```diff
--- a/.env.example
+++ b/.env.example
@@ -47,3 +47,8 @@
 PUBLIC_REPS=0
 PUBLIC_FLUSH_S=10
 GROUND_INGEST_SECRET=
+
+# Outdoor weather importer (nodes/weather, D45). The bench location: decimal degrees, rounded to 1 decimal before use.
+# Never commit .env. The location is never posted, logged or shown.
+WEATHER_LAT=
+WEATHER_LON=
```

Generate `data/replay/signals-synthetic-28d.jsonl` (do not hand-write it):

```bash
python -m hub.sim.signals_synth --out data/replay/signals-synthetic-28d.jsonl
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q nodes/weather/tests/test_weather.py
```

Expected:

```text
7 passed, 1 skipped
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add .env.example DATA_SOURCES.md data/replay/signals-synthetic-28d.jsonl hub/sim/signals_synth.py nodes/weather/__init__.py nodes/weather/__main__.py nodes/weather/location.py nodes/weather/mapper.py nodes/weather/provider.py nodes/weather/tests/__init__.py nodes/weather/tests/test_weather.py
git commit -m "feat(weather): outdoor reference importer (provider seam) and Earth lines in the replay"
```

### Task 9: The INMET station adapter (after the token arrives)

Needs the token from Task 5. INMET publishes no API manual online (checked 2026-11-15); the facts below come from
the INMET.jl client (MIT, `JuliaClimate/INMET.jl`) and INMET's portal, and **Step 1 checks every one of them against
the live server first**. Change the code to match what the server returns, not the other way round.

Facts to check (from INMET.jl and the portal):

| Item | Expected |
|---|---|
| Station list | `GET https://apitempo.inmet.gov.br/estacoes/T` (automatic stations), no token; fields `CD_ESTACAO`, `VL_LATITUDE`, `VL_LONGITUDE` |
| Hourly data | `GET https://apitempo.inmet.gov.br/token/estacao/{YYYY-MM-DD}/{YYYY-MM-DD}/{CD_ESTACAO}/{token}` (INMET.jl builds it with an empty segment, `estacao//`; check which the server accepts) |
| Time | `DT_MEDICAO` (`2026-11-20`) and `HR_MEDICAO` (`1200`), UTC per the portal |
| Values | strings: `TEM_INS` (°C), `UMD_INS` (%), `PRE_INS` (station pressure, mbar = hPa) |
| Missing | `null`; the portal also lists `9999`, `"Null"` and empty fields |
| Window | the portal keeps the last 90 days of hourly data; the importer asks for 2 days |

**Files:**
- Create: `nodes/weather/provider_inmet.py`
- Create: `nodes/weather/tests/fixtures/inmet-sample.json`
- Create: `nodes/weather/tests/test_provider_inmet.py`
- Modify: `nodes/weather/provider.py` (`default_provider` returns the INMET adapter when `WEATHER_STATION` and `INMET_TOKEN` are set)
- Modify: `nodes/weather/__main__.py` (a `stations` command: the 3 nearest automatic stations to the coarse cell, printed as code and distance in km only)
- Modify: `.env.example` (`WEATHER_STATION=` and `INMET_TOKEN=`, empty)
- Modify: `DATA_SOURCES.md` (the "Earth weather" entry: endpoints, fields, units, missing values, access date, "raw, unvalidated")

- [ ] **Step 1: Check the live server** with the token in `.env` (never on the command line, where it lands in shell
  history): fetch the station list and two days of one station, and compare the field names, time format and
  missing values with the table. Fix the table in this plan's PR if anything differs.
- [ ] **Step 2: Save one real response as the fixture**, then strip every location field before saving it:
  `VL_LATITUDE`, `VL_LONGITUDE`, `VL_ALTITUDE`, `DC_NOME`, `UF`, and replace `CD_ESTACAO` with `"X000"`. Keep only the
  time and value fields. Include at least one hour with a `null` value; if none occurs, set one by hand and say so in
  the test.
- [ ] **Step 3: Write the failing tests**

```python
import json
from datetime import UTC, datetime
from pathlib import Path

from nodes.weather.mapper import HourRow
from nodes.weather.provider_inmet import parse

FIX = Path(__file__).parent / "fixtures" / "inmet-sample.json"


def rows():
    return parse(json.loads(FIX.read_text(encoding="utf-8")))


def test_sample_parses_to_utc_hour_rows_in_order():
    rs = rows()
    assert rs and all(isinstance(r, HourRow) and r.t.tzinfo == UTC for r in rs)
    assert [r.t for r in rs] == sorted(r.t for r in rs)


def test_values_and_units():
    r = next(r for r in rows() if r.temp_c is not None)
    assert -90 < r.temp_c < 60 and 0 <= r.rh_pct <= 100 and 850 < r.p_hpa < 1090


def test_missing_markers_become_none_never_zero():
    data = [{"DT_MEDICAO": "2026-11-20", "HR_MEDICAO": "1200", "TEM_INS": None, "UMD_INS": "9999",
             "PRE_INS": ""}]  # fmt: skip
    [r] = parse(data)
    assert r.t == datetime(2026, 11, 20, 12, tzinfo=UTC)
    assert (r.temp_c, r.rh_pct, r.p_hpa) == (None, None, None)


def test_the_fixture_holds_no_location():
    text = FIX.read_text(encoding="utf-8")
    for key in ("VL_LATITUDE", "VL_LONGITUDE", "VL_ALTITUDE", "DC_NOME", '"UF"'):
        assert key not in text
```

- [ ] **Step 4: Run them and see them fail** (`python -m pytest -q nodes/weather/tests/test_provider_inmet.py`):
  `ModuleNotFoundError: No module named 'nodes.weather.provider_inmet'`.
- [ ] **Step 5: Write the adapter**: a pure `parse(data: list[dict]) -> list[HourRow]` (UTC times from `DT_MEDICAO` and
  `HR_MEDICAO`; `None`, `""`, `"Null"` and `"9999"` → `None`; strings to floats; sorted), and
  `InmetProvider(station, token, http).hours(start, end)` doing one GET for the dates that cover `[start, end]` and
  returning only rows in that range. Use `httpx` with a 10 s timeout and a generic `User-Agent` such as
  `habitat-hub-weather/1`. The token is part of the URL path, so **never log or print the URL**: on an HTTP error, raise
  with the status code only. Then make `default_provider` return `InmetProvider` when both `.env` values are set.
- [ ] **Step 6: Run the tests** (the new ones and `nodes/weather/tests`) and see them pass, including
  `test_the_bench_location_is_in_no_tracked_file`. Extend that test to check the `WEATHER_STATION` and `INMET_TOKEN`
  values too.
- [ ] **Step 7: Dry run** against the server: `python -m nodes.weather pull --hours 6 --dry-run` prints counts only.
- [ ] **Step 8: Fill the `DATA_SOURCES.md` entry** and commit:

```bash
git add nodes/weather .env.example DATA_SOURCES.md
git commit -m "feat(weather): INMET automatic-station adapter (raw hourly data, token in .env)"
```

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat: D45 reference feeds (ISS storage, outdoor weather importer)" --body "Implements D45 slice 3 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 5–9."
```

---

## Slice 4: food, body mass, lift and cross-reference signals (PR 4)

Branch `feat/d45-signals-more`. Completes the 19-signal catalogue.

### Task 10: Daily trends: body mass and water logged

Daily values per local day: the last body-mass entry, the sum of water logged. A day with no entry has no value.

**Files:**
- Create: `hub/signals/daily.py`
- Create: `hub/tests/signals/test_daily.py`
- Modify: `hub/signals/catalogue.py`
- Modify: `hub/signals/engine.py`

**Interfaces:**
- Consumes: Task 2's `inputs`, `common.trend_signal`.
- Produces: `hub/signals/daily.py` with `by_day(rows, tz, how: "sum"|"last"|"max") -> dict[date, (datetime, float)]` and `daily_trend`; catalogue `body_mass_30d`, `water_14d`; builders `("trend", "daily_last")`, `("trend", "daily_sum")`.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/signals/test_daily.py`:

```python
from datetime import timedelta

import pytest

from hub.tests.signals.kit import END, meal, one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_water_trend_skips_days_without_a_meal(rig):
    for d in range(14, 0, -1):
        if d % 5 == 0:
            continue  # no meal logged that day: no value, not zero
        meal(rig, END - timedelta(days=d), 1500 + 50 * (14 - d))
    s = one(rig, "water_14d")
    assert s.state == "notable" and s.headline_key == "signals.trend.up"
    # The window is (at - 14 d, at]: day 14 falls just outside, and days 10 and 5 have no meal.
    assert s.method.n == 11 and s.value.per == "day" and s.value.unit == "mL"


def test_water_trend_needs_three_quarters_of_the_days(rig):
    for d in range(9, 0, -1):
        meal(rig, END - timedelta(days=d), 1500)
    s = one(rig, "water_14d")
    assert s.state == "not_enough_data"
    assert (s.missing[0].key, s.missing[0].need, s.missing[0].have) == (
        "signals.missing.days",
        11,
        9,
    )


def test_body_mass_keeps_the_last_weigh_in_of_each_day(rig):
    for d in range(28, 0, -1):
        day = END - timedelta(days=d)
        # an earlier, mistyped entry that day, then the real weigh-in
        put_ref(rig, "body_mass", 30.0, day - timedelta(hours=1), node="manual", dev="manual",
                src="self", crew="crew-a")  # fmt: skip
        put_ref(rig, "body_mass", 80.0 + 0.05 * d, day, node="manual", dev="manual", src="self",
                crew="crew-a")  # fmt: skip
    s = one(rig, "body_mass_30d")
    assert s.headline_key == "signals.trend.down" and s.value.unit == "kg"
    assert s.value.estimate == pytest.approx(-0.05, abs=0.01)


def test_a_crew_less_meal_never_counts_for_a_crew(rig):
    for d in range(13, 0, -1):
        rig.put("intake_water_ml", 1500, END - timedelta(days=d), node="food", dev="catalog",
                src="self", crew=None)  # logged without a crew  # fmt: skip
    s = one(rig, "water_14d")
    assert s.state == "not_enough_data" and s.missing[0].have == 0 and not s.inputs
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_daily.py
```

Expected (first error and summary):

```text
E       KeyError: 'water_14d'
1 failed in 0.08s
```

- [ ] **Step 3: Write the implementation**

Create `hub/signals/daily.py`:

```python
"""Daily body and food values (per crew): body mass and water-logged trends (D45 §6.5, §7)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from hub.signals import inputs as I
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, trend_signal
from hub.signals.types import Signal
from hub.store import StoredReading

How = Literal["sum", "last", "max"]


def by_day(
    rows: Iterable[StoredReading], tz: ZoneInfo, how: How
) -> dict[date, tuple[datetime, float]]:
    """{local day: (time of the day's last row, value)}. A day without a row is absent, never 0."""
    out: dict[date, tuple[datetime, float]] = {}
    for t, v in I.points(rows):
        d = t.astimezone(tz).date()
        prev = out.get(d)
        if prev is None:
            out[d] = (t, v)
        elif how == "sum":
            out[d] = (max(prev[0], t), prev[1] + v)
        elif how == "max":
            out[d] = (max(prev[0], t), max(prev[1], v))
        elif t >= prev[0]:
            out[d] = (t, v)
    return out


def daily_trend(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    assert spec.ind is not None
    start = ctx.at - spec.window
    rows, replay = I.choose(I.ok_rows(ctx.store, spec.ind, start, ctx.at, crew))
    days = by_day(rows, ctx.tz, "sum" if spec.source == "daily_sum" else "last")
    first = start.astimezone(ctx.tz).date()
    pts = [(float((d - first).days), v) for d, (_, v) in sorted(days.items())]
    common = {
        "inputs": I.describe(rows, ctx.at), "replay": replay,
        "series": I.series_out([tv for _, tv in sorted(days.items())]),
    }  # fmt: skip
    return trend_signal(spec, ctx, crew, pts, spec.window.days, start, "day",
                        "signals.missing.days", **common)  # fmt: skip
```

Modify `hub/signals/catalogue.py`:

```diff
--- a/hub/signals/catalogue.py
+++ b/hub/signals/catalogue.py
@@ -68,6 +68,11 @@
     # 30-minute blocks: ISS Live pushes a value only when it changes (team owner, 2026-11-15).
     Spec("iss_ppco2_6h", "trend", "cabin", "iss_ppco2", 6 * H, 30 * MIN, 10, 0.75, False,
          limits=(INDEPENDENCE, ISS)),
+    # slice 4: food, body mass, lift and cross-references
+    Spec("body_mass_30d", "trend", "daily_last", "body_mass", 30 * D, None, 10, 0.75, True,
+         limits=(INDEPENDENCE, LOGGED_ONLY)),
+    Spec("water_14d", "trend", "daily_sum", "intake_water_ml", 14 * D, None, 10, 0.75, True,
+         limits=(INDEPENDENCE, LOGGED_ONLY)),
 )  # fmt: skip
 
 BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
```

Modify `hub/signals/engine.py`:

```diff
--- a/hub/signals/engine.py
+++ b/hub/signals/engine.py
@@ -7,7 +7,7 @@
 from datetime import datetime
 from zoneinfo import ZoneInfo
 
-from hub.signals import body, cabin
+from hub.signals import body, cabin, daily
 from hub.signals.catalogue import BY_ID, CATALOGUE, Spec
 from hub.signals.common import Ctx
 from hub.signals.types import Signal
@@ -24,6 +24,8 @@
     ("baseline", "night_rest_hr"): body.baseline,
     ("baseline", "night_value"): body.baseline,
     ("trend", "night_rest_hr"): body.night_trend,
+    ("trend", "daily_last"): daily.daily_trend,
+    ("trend", "daily_sum"): daily.daily_trend,
 }
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_daily.py
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/signals/catalogue.py hub/signals/daily.py hub/signals/engine.py hub/tests/signals/test_daily.py
git commit -m "feat(signals): body-mass and water-logged trends"
```

### Task 11: Lift signals: across sets, within a set, camera-tilt agreement

Camera sets of the crew: work per rep divided by g (mass × ROM, so sets at any gravity compare), tempo and the tilt witness. Replay sets (node `sim-1`) never pool with real ones.

**Files:**
- Create: `hub/signals/lift.py`
- Create: `hub/tests/signals/test_lift.py`
- Modify: `hub/signals/catalogue.py`
- Modify: `hub/signals/engine.py`

**Interfaces:**
- Consumes: `hub.exercise.latest_reps`, `hub.tilt.tilt_for_rep`, `Store.session_rows`, `Store.reps_for_session`; Task 2's `common`.
- Produces: `hub/signals/lift.py` with `SetRollup`, `sets(ctx, crew, spec) -> (list[SetRollup], replay)`, `work_across_sets`, `work_within_set`, `tilt_agreement`, `daily_work(ss, tz)`; catalogue `lift_work_sets`, `lift_within_set`, `lift_tilt_agreement` (unit `kg_m` or `ms`); builders `lift_sets`, `lift_within`, `lift_tilt`.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/signals/test_lift.py`:

```python
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
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_lift.py
```

Expected (first error and summary):

```text
E       KeyError: 'lift_within_set'
1 failed in 0.09s
```

- [ ] **Step 3: Write the implementation**

Create `hub/signals/lift.py`:

```python
"""Camera sets (per crew): work per rep across sets, within the latest set, and the camera-tilt
agreement (D45 §6.5, §7). Work is mechanical work on the load, never food energy."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from hub.exercise import latest_reps
from hub.signals import methods as M
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal, spec_unit, trend_signal
from hub.signals.types import Input, Missing, Signal, Value
from hub.store import StoredRep
from hub.tilt import tilt_for_rep
from hub.timeutil import parse_iso, to_iso

REPLAY_NODES = frozenset({"sim-1"})
PRIOR_SETS = 14


@dataclass(frozen=True)
class SetRollup:
    session: str
    exercise: str | None
    started_at: datetime
    works: list[float]  # work_j / g per rep, in rep order (mass x ROM, so sets at any g compare)
    tilt_share: float | None  # share of reps with a tilt witness, of the reps that could have one
    tilt_offset_ms: float | None  # median |offset| of the witnessed reps
    replay: bool
    reps: list[StoredRep]

    @property
    def work(self) -> float:
        return statistics.median(self.works)


def _rollup(ctx: Ctx, row: tuple) -> SetRollup | None:
    cam = latest_reps([r for r in ctx.store.reps_for_session(row[0]) if r.src == "camera"])
    usable = [r for r in cam if r.g > 0 and r.work_j is not None]
    if not usable:
        return None
    witness = [tilt_for_rep(ctx.store, r) for r in usable]
    could = [w for w in witness if w is not None]
    seen = [w for w in could if w["seen"]]
    return SetRollup(
        session=row[0], exercise=row[6], started_at=parse_iso(row[4]),
        works=[r.work_j / r.g for r in usable],  # type: ignore[operator]
        tilt_share=len(seen) / len(could) if could else None,
        tilt_offset_ms=statistics.median(abs(w["offset_ms"]) for w in seen) if seen else None,
        replay=any(r.node in REPLAY_NODES for r in usable), reps=usable,
    )  # fmt: skip


def sets(ctx: Ctx, crew: str | None, spec: Spec) -> tuple[list[SetRollup], bool]:
    """The crew's camera sets started in the window, ascending, real sets only when any exist."""
    start = ctx.at - spec.window
    rows = [
        r for r in ctx.store.session_rows() if r[3] == crew and start < parse_iso(r[4]) <= ctx.at
    ]
    rolled = [s for s in (_rollup(ctx, r) for r in rows) if s is not None]
    rolled.sort(key=lambda s: s.started_at)
    real = [s for s in rolled if not s.replay]
    if real:
        return real, False
    return rolled, bool(rolled)


def _inputs(ss: list[SetRollup], at: datetime) -> list[Input]:
    reps = [r for s in ss for r in s.reps]
    if not reps:
        return []
    times = sorted(r.measured_at for r in reps)
    age = max(0.0, (at - parse_iso(times[-1])).total_seconds())
    return [Input("work_j", "camera", "camera", reps[0].node, len(reps), times[0], times[-1], age)]


def work_across_sets(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    if ss:
        ss = [s for s in ss if s.exercise == ss[-1].exercise]  # one exercise: the latest set's
    common = {
        "inputs": _inputs(ss, ctx.at), "replay": replay,
        "series": [[to_iso(s.started_at), s.work] for s in ss],
        "detail": {"exercise": ss[-1].exercise if ss else None},
    }  # fmt: skip
    pts = [((s.started_at - start).total_seconds() / 86400, s.work) for s in ss]
    return trend_signal(spec, ctx, crew, pts, max(len(pts), 1), start, "day",
                        "signals.missing.sets", **common)  # fmt: skip


def work_within_set(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    last = ss[-1] if ss else None
    works = last.works if last else []
    common = {
        "inputs": _inputs([last] if last else [], ctx.at), "replay": replay,
        "series": [[i + 1, w] for i, w in enumerate(works)],
        "detail": {"session": last.session if last else None,
                   "exercise": last.exercise if last else None},
    }  # fmt: skip
    pts = [(float(i + 1), w) for i, w in enumerate(works)]
    return trend_signal(spec, ctx, crew, pts, max(len(pts), 1), start, "rep",
                        "signals.missing.reps", **common)  # fmt: skip


def tilt_agreement(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    start = ctx.at - spec.window
    ss, replay = sets(ctx, crew, spec)
    withv = [s for s in ss if s.tilt_offset_ms is not None]
    common = {
        "inputs": _inputs(withv, ctx.at), "replay": replay,
        "series": [[to_iso(s.started_at), s.tilt_offset_ms] for s in withv],
        "detail": {"tilt_share": withv[-1].tilt_share if withv else None},
    }  # fmt: skip
    meth = method(spec, ctx, "own_baseline", M.BASELINE_REF, max(len(withv) - 1, 0), start, None,
                  alpha=None)  # fmt: skip
    if len(withv) < 2:
        return nodata(spec, crew, meth, [Missing("signals.missing.priorSets", spec.min_n,
                                                 max(len(withv) - 1, 0))], **common)  # fmt: skip

    def range_before(i: int) -> M.Baseline | None:
        prior = [s.tilt_offset_ms for s in withv[max(0, i - PRIOR_SETS) : i]]
        return M.own_baseline(prior, min_n=spec.min_n)  # type: ignore[arg-type]

    b = range_before(len(withv) - 1)
    if b is None:
        n_prior = min(len(withv) - 1, PRIOR_SETS)
        key = "signals.missing.priorSets" if n_prior < spec.min_n else "signals.missing.spread"
        return nodata(spec, crew, meth, [Missing(key, spec.min_n, n_prior)], **common)
    x = withv[-1].tilt_offset_ms
    assert x is not None
    value = Value(x, b.low, b.high, spec_unit(spec))
    headline = ("signals.baseline.above" if x > b.high else
                "signals.baseline.below" if x < b.low else "signals.baseline.inside")  # fmt: skip
    prev = range_before(len(withv) - 2)
    notable = (M.outside(x, b, spec.side) and prev is not None
               and M.outside(withv[-2].tilt_offset_ms, prev, spec.side))  # type: ignore[arg-type]  # fmt: skip
    return signal(spec, crew, "notable" if notable else "steady", headline, value, meth, **common)


def daily_work(ss: list[SetRollup], tz) -> dict:
    """{local day of the set start: sum of work_j / g over the day's sets}."""
    out: dict = {}
    for s in ss:
        d = s.started_at.astimezone(tz).date()
        out[d] = out.get(d, 0.0) + sum(s.works)
    return out
```

Modify `hub/signals/catalogue.py`:

```diff
--- a/hub/signals/catalogue.py
+++ b/hub/signals/catalogue.py
@@ -73,6 +73,12 @@
          limits=(INDEPENDENCE, LOGGED_ONLY)),
     Spec("water_14d", "trend", "daily_sum", "intake_water_ml", 14 * D, None, 10, 0.75, True,
          limits=(INDEPENDENCE, LOGGED_ONLY)),
+    Spec("lift_work_sets", "trend", "lift_sets", None, 60 * D, None, 10, 0.0, True,
+         limits=(INDEPENDENCE, CAMERA, NOT_FOOD), unit="kg_m"),
+    Spec("lift_within_set", "trend", "lift_within", None, 60 * D, None, 6, 0.0, True,
+         limits=(INDEPENDENCE, CAMERA, NOT_FOOD), unit="kg_m"),
+    Spec("lift_tilt_agreement", "baseline", "lift_tilt", None, 60 * D, None, 7, 0.0, True,
+         side="high", limits=(RIG_CHECK,), unit="ms"),
 )  # fmt: skip
 
 BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
```

Modify `hub/signals/engine.py`:

```diff
--- a/hub/signals/engine.py
+++ b/hub/signals/engine.py
@@ -7,7 +7,7 @@
 from datetime import datetime
 from zoneinfo import ZoneInfo
 
-from hub.signals import body, cabin, daily
+from hub.signals import body, cabin, daily, lift
 from hub.signals.catalogue import BY_ID, CATALOGUE, Spec
 from hub.signals.common import Ctx
 from hub.signals.types import Signal
@@ -26,6 +26,9 @@
     ("trend", "night_rest_hr"): body.night_trend,
     ("trend", "daily_last"): daily.daily_trend,
     ("trend", "daily_sum"): daily.daily_trend,
+    ("trend", "lift_sets"): lift.work_across_sets,
+    ("trend", "lift_within"): lift.work_within_set,
+    ("baseline", "lift_tilt"): lift.tilt_agreement,
 }
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_lift.py
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/signals/catalogue.py hub/signals/engine.py hub/signals/lift.py hub/tests/signals/test_lift.py
git commit -m "feat(signals): lift signals across sets, within a set, and camera-tilt agreement"
```

### Task 12: Lagged cross-references

Side-by-side pairs, never notable. `cabin_vs_earth` shows every lag from 0 to 3 h and picks none. The replay test gains the food, cross-reference and lift checks.

**Files:**
- Create: `hub/signals/pairs.py`
- Create: `hub/tests/signals/test_pairs.py`
- Modify: `hub/signals/catalogue.py`
- Modify: `hub/signals/engine.py`
- Modify: `hub/tests/signals/test_replay_signals.py`

**Interfaces:**
- Consumes: Task 10's `by_day`, Task 11's `sets` and `daily_work`, Task 2's `body.nightly`, Task 1's `spearman` and `lagged_pairs`.
- Produces: `hub/signals/pairs.py` with `training_vs_rest_hr`, `last_meal_vs_sleep`, `space_weather_vs_sleep`, `cabin_vs_earth`, `CABIN_LAGS_H = (0, 1, 2, 3)`; headline keys `signals.pair.few|rho`; `detail["lags"]` entries `{lag_h, n, rho, low, high}`.

- [ ] **Step 1: Write the failing tests**

Create `hub/tests/signals/test_pairs.py`:

```python
from datetime import timedelta

import pytest

from hub.signals.engine import evaluate
from hub.tests.signals.kit import END, TZ, meal, night, one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_last_meal_vs_sleep_few_pairs_shows_table_only(rig):
    for d in range(6, 0, -1):
        meal(rig, END - timedelta(days=d) + timedelta(hours=9), 500)  # 16:00 local
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "last_meal_vs_sleep")
    assert s.state == "steady" and s.headline_key == "signals.pair.few" and s.value is None
    assert len(s.pairs) == 6 and s.pairs[0][1] == pytest.approx(16.0)


def test_last_meal_vs_sleep_rho_at_20_pairs_is_never_notable(rig):
    for d in range(22, 0, -1):
        hour = 9 + (d % 5)  # meals 16:00-20:00 local
        meal(rig, END - timedelta(days=d) + timedelta(hours=hour), 500)
        night(rig, END - timedelta(days=d - 1), 8.5 - 0.3 * (d % 5))
    s = one(rig, "last_meal_vs_sleep")
    assert s.headline_key == "signals.pair.rho" and s.state == "steady"
    assert s.value.unit == "rho" and s.value.low <= s.value.estimate <= s.value.high
    assert not s.can_trigger


def test_space_weather_pairs_never_mix_replay_and_real(rig):
    for d in range(5, 0, -1):
        put_ref(
            rig, "space_weather", 1, END - timedelta(days=d), node="nasa", dev="DONKI", src="nasa"
        )
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "space_weather_vs_sleep")
    assert len(s.pairs) == 5 and not s.replay
    assert all(i.src != "replay" for i in s.inputs)


def test_cabin_vs_earth_lags_and_no_best_lag(rig):
    for h in range(30, 0, -1):
        at = END - timedelta(hours=h)
        put_ref(rig, "earth_temp", 15 + (h % 6), at, node="earth-1", dev="WEATHER", src="ref")
        rig.put("cabin_temp", 22 + 0.2 * (h % 6), at)
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.value is None and [x["lag_h"] for x in s.detail["lags"]] == [0, 1, 2, 3]
    assert s.detail["lags"][0]["n"] == 30 and s.detail["lags"][0]["rho"] is not None


def test_a_failing_builder_leaves_the_others(rig, monkeypatch, caplog):
    from hub.signals import engine

    def boom(ctx, spec, crew):
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.BUILDERS, ("trend", "cabin"), boom)
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a"], at=END, tz=TZ)
    ids = {s.id for s in out}
    assert "cabin_temp_6h" not in ids and "cabin_rh_ttl" in ids and "boom" in caplog.text
```

Modify `hub/tests/signals/test_replay_signals.py`:

```diff
--- a/hub/tests/signals/test_replay_signals.py
+++ b/hub/tests/signals/test_replay_signals.py
@@ -65,6 +65,23 @@
     assert signals[("sleep_baseline", "crew-a")].state in ("steady", "notable")
 
 
+def test_food_mass_and_cross_references(signals):
+    assert signals[("water_14d", "crew-a")].headline_key == "signals.trend.up"
+    assert signals[("water_14d", "crew-c")].state == "not_enough_data"  # every third day only
+    assert signals[("body_mass_30d", "crew-a")].headline_key == "signals.trend.down"
+    meal = signals[("last_meal_vs_sleep", "crew-a")]
+    assert meal.headline_key == "signals.pair.rho" and meal.state == "steady"
+    sw = signals[("space_weather_vs_sleep", "crew-a")]
+    assert sw.state == "steady" and len(sw.pairs) >= 20
+    ce = signals[("cabin_vs_earth", None)]
+    assert [x["lag_h"] for x in ce.detail["lags"]] == [0, 1, 2, 3] and ce.value is None
+
+
+def test_lift_signals_say_not_enough_data_on_the_replay(signals):
+    for sid in ("lift_work_sets", "lift_within_set", "lift_tilt_agreement", "training_vs_rest_hr"):
+        assert signals[(sid, "crew-a")].state == "not_enough_data", sid
+
+
 def test_committed_replay_matches_the_generator(tmp_path):
     committed = REPO / "data" / "replay" / "signals-synthetic-28d.jsonl"
     fresh = tmp_path / "fresh.jsonl"
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_pairs.py hub/tests/signals/test_replay_signals.py
```

Expected (first error and summary):

```text
E       KeyError: 'last_meal_vs_sleep'
1 failed in 0.11s
```

- [ ] **Step 3: Write the implementation**

Create `hub/signals/pairs.py`:

```python
"""Lagged cross-references (D45 §6.4): side by side, never notable, never a cause.

Both sides of a pair come from the same mode: the second side follows the first side's real or
replay choice, so a replay value is never paired with a real one.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from hub.contract import INTAKE_ORDER
from hub.signals import inputs as I
from hub.signals import lift
from hub.signals import methods as M
from hub.signals.body import nightly
from hub.signals.catalogue import Spec
from hub.signals.common import Ctx, method, nodata, signal
from hub.signals.daily import by_day
from hub.signals.types import Missing, Signal, Value

DAY = timedelta(days=1)
CABIN_LAGS_H = (0, 1, 2, 3)


def _pair_signal(ctx: Ctx, spec: Spec, crew: str | None, xs: dict, ys: dict, lag: timedelta,
                 **common) -> Signal:  # fmt: skip
    start = ctx.at - spec.window
    pairs = M.lagged_pairs(xs, ys, lag=lag)
    meth = method(spec, ctx, "spearman_fisher_z", M.SPEARMAN_REF, len(pairs), start, None)
    table = [[str(k), x, y] for k, x, y in pairs]
    if not pairs:
        return nodata(spec, crew, meth, [Missing("signals.missing.pairs", spec.min_n, 0)],
                      **common)  # fmt: skip
    sp = M.spearman([(x, y) for _, x, y in pairs], min_n=spec.min_n)
    if sp is None:
        return signal(spec, crew, "steady", "signals.pair.few", None, meth, pairs=table, **common)
    value = Value(sp.rho, sp.low, sp.high, "rho")
    return signal(spec, crew, "steady", "signals.pair.rho", value, meth, pairs=table, **common)


def _sleep(ctx: Ctx, spec: Spec, crew: str | None):
    """{day d: sleep_h of the night that ends on day d + 1}, keyed by the night's end day."""
    vals, used, replay = nightly(ctx, "night_value", "sleep_h", crew, spec.window.days)
    return {d: v for d, (_, v) in vals.items()}, used, replay


def training_vs_rest_hr(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    vals, used, replay = nightly(ctx, "night_rest_hr", "hr", crew, spec.window.days)
    ys = {d: v for d, (_, v) in vals.items()}
    ss, _ = lift.sets(ctx, crew, spec)
    ss = [s for s in ss if s.replay == replay]
    xs = lift.daily_work(ss, ctx.tz)
    common = {"inputs": I.describe(used, ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def last_meal_vs_sleep(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    ys, used, replay = _sleep(ctx, spec, crew)
    start = ctx.at - spec.window
    rows = [r for ind in INTAKE_ORDER for r in I.ok_rows(ctx.store, ind, start, ctx.at, crew)]
    rows = I.same_mode(rows, replay)
    last = by_day(rows, ctx.tz, "last")
    # x is the local clock time of the day's last logged meal, in hours (19.5 = 19:30)
    xs = {}
    for d, (t, _) in last.items():
        lt = t.astimezone(ctx.tz)
        xs[d] = lt.hour + lt.minute / 60
    common = {"inputs": I.describe([*used, *rows], ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def space_weather_vs_sleep(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    ys, used, replay = _sleep(ctx, spec, crew)
    start = ctx.at - spec.window
    rows = I.same_mode(I.ok_rows(ctx.store, "space_weather", start, ctx.at, None), replay)
    xs = {d: v for d, (_, v) in by_day(rows, ctx.tz, "max").items()}
    common = {"inputs": I.describe([*used, *rows], ctx.at), "replay": replay}
    return _pair_signal(ctx, spec, crew, xs, ys, DAY, **common)


def _hourly(pts: list[tuple[datetime, float]]) -> dict[datetime, float]:
    groups: dict[datetime, list[float]] = {}
    for t, v in pts:
        groups.setdefault(t.replace(minute=0, second=0, microsecond=0), []).append(v)
    return {h: statistics.median(v) for h, v in groups.items()}


def cabin_vs_earth(ctx: Ctx, spec: Spec, crew: str | None) -> Signal:
    """Hourly medians side by side at lags 0-3 h. No lag is picked as the best one."""
    start = ctx.at - spec.window
    cabin, replay = I.choose(I.ok_rows(ctx.store, "cabin_temp", start, ctx.at, None))
    earth = I.same_mode(I.ok_rows(ctx.store, "earth_temp", start, ctx.at, None), replay)
    xs, ys = _hourly(I.points(earth)), _hourly(I.points(cabin))
    meth = method(spec, ctx, "spearman_fisher_z", M.SPEARMAN_REF, 0, start, None)
    common = {"inputs": I.describe([*cabin, *earth], ctx.at), "replay": replay}
    lags, table = [], []
    for h in CABIN_LAGS_H:
        pairs = M.lagged_pairs(xs, ys, lag=timedelta(hours=h))  # earth at t, cabin at t + h
        sp = M.spearman([(x, y) for _, x, y in pairs], min_n=spec.min_n)
        lags.append({"lag_h": h, "n": len(pairs), "rho": sp.rho if sp else None,
                     "low": sp.low if sp else None, "high": sp.high if sp else None})  # fmt: skip
        table += [[I.to_iso(k), x, y, h] for k, x, y in pairs]
    if not table:
        return nodata(spec, crew, meth, [Missing("signals.missing.pairs", spec.min_n, 0)],
                      detail={"lags": lags}, **common)  # fmt: skip
    head = "signals.pair.rho" if any(x["rho"] is not None for x in lags) else "signals.pair.few"
    return signal(spec, crew, "steady", head, None, meth, pairs=table, detail={"lags": lags},
                  **common)  # fmt: skip
```

Modify `hub/signals/catalogue.py`:

```diff
--- a/hub/signals/catalogue.py
+++ b/hub/signals/catalogue.py
@@ -79,6 +79,14 @@
          limits=(INDEPENDENCE, CAMERA, NOT_FOOD), unit="kg_m"),
     Spec("lift_tilt_agreement", "baseline", "lift_tilt", None, 60 * D, None, 7, 0.0, True,
          side="high", limits=(RIG_CHECK,), unit="ms"),
+    Spec("cabin_vs_earth", "lagged_pair", "cabin_earth", None, 7 * D, None, 20, 0.0, False,
+         limits=(OWN_DATA, NEIGHBOUR_HOURS, EARTH)),
+    Spec("training_vs_rest_hr", "lagged_pair", "training_rest_hr", None, 60 * D, None, 20, 0.0,
+         True, limits=(OWN_DATA, CAMERA, RING)),
+    Spec("last_meal_vs_sleep", "lagged_pair", "meal_sleep", None, 60 * D, None, 20, 0.0, True,
+         limits=(OWN_DATA, LOGGED_ONLY, RING)),
+    Spec("space_weather_vs_sleep", "lagged_pair", "space_weather_sleep", None, 60 * D, None, 20,
+         0.0, True, limits=(OWN_DATA, ON_EARTH)),
 )  # fmt: skip
 
 BY_ID: dict[str, Spec] = {s.id: s for s in CATALOGUE}
```

Modify `hub/signals/engine.py`:

```diff
--- a/hub/signals/engine.py
+++ b/hub/signals/engine.py
@@ -7,7 +7,7 @@
 from datetime import datetime
 from zoneinfo import ZoneInfo
 
-from hub.signals import body, cabin, daily, lift
+from hub.signals import body, cabin, daily, lift, pairs
 from hub.signals.catalogue import BY_ID, CATALOGUE, Spec
 from hub.signals.common import Ctx
 from hub.signals.types import Signal
@@ -29,6 +29,10 @@
     ("trend", "lift_sets"): lift.work_across_sets,
     ("trend", "lift_within"): lift.work_within_set,
     ("baseline", "lift_tilt"): lift.tilt_agreement,
+    ("lagged_pair", "cabin_earth"): pairs.cabin_vs_earth,
+    ("lagged_pair", "training_rest_hr"): pairs.training_vs_rest_hr,
+    ("lagged_pair", "meal_sleep"): pairs.last_meal_vs_sleep,
+    ("lagged_pair", "space_weather_sleep"): pairs.space_weather_vs_sleep,
 }
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_pairs.py hub/tests/signals/test_replay_signals.py
```

Expected:

```text
13 passed
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/signals/catalogue.py hub/signals/engine.py hub/signals/pairs.py hub/tests/signals/test_pairs.py hub/tests/signals/test_replay_signals.py
git commit -m "feat(signals): lagged cross-references (side by side, never notable)"
```

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat(signals): D45 food, lift and cross-reference signals" --body "Implements D45 slice 4 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 10–12."
```

---

## Slice 5: the self-check trigger (PR 5)

Branch `feat/d45-signals-trigger`. A notable ★ signal may open a self-check; it never alerts.

### Task 13: Prompt kinds `signal_cabin` and `signal_body`

Two prompt kinds the trigger will use. They can only be created with a signal snapshot, so they cannot be made by hand.

**Files:**
- Modify: `hub/prompts.py`
- Modify: `hub/tests/test_prompts.py`

**Interfaces:**
- Consumes: `hub/prompts.py` `PROMPT_ASKS`, `PromptService.create`.
- Produces: kinds `signal_cabin` → `("symptom",)` and `signal_body` → `("symptom", "mood")`; `SIGNAL_KINDS`; `PromptService.create(kind, crew, *, trigger_reading_id=None, rule_id=None, trigger: dict | None = None)`; a signal kind without a `trigger`, or a `trigger` on another kind, raises `PromptError("bad_value:kind")`.

- [ ] **Step 1: Write the failing test**

Modify `hub/tests/test_prompts.py`:

```diff
--- a/hub/tests/test_prompts.py
+++ b/hub/tests/test_prompts.py
@@ -111,4 +111,10 @@
     assert client.post("/api/prompts", json={"kind": "morning", "crew": "crew-z"}).json() == {
         "reason": "bad_crew"
     }
-    assert set(PROMPT_ASKS) == {"morning", "post_exercise", "cabin_trigger"}
+    assert set(PROMPT_ASKS) == {
+        "morning", "post_exercise", "cabin_trigger", "signal_cabin", "signal_body",
+    }  # fmt: skip
+    # Signal prompts are opened only by the signals trigger, with a snapshot (D45 §8.2).
+    assert client.post("/api/prompts", json={"kind": "signal_body", "crew": "crew-a"}).json() == {
+        "reason": "bad_value:kind"
+    }
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/test_prompts.py
```

Expected (first error and summary):

```text
E       AssertionError: assert {'cabin_trigg...ost_exercise'} == {'cabin_trigg...signal_cabin'}
1 failed, 7 passed, 1 warning in 1.14s
```

- [ ] **Step 3: Write the implementation**

Modify `hub/prompts.py`:

```diff
--- a/hub/prompts.py
+++ b/hub/prompts.py
@@ -24,7 +24,11 @@
     "morning": ("body_temp", "hr", "sleep_h", "mood"),
     "post_exercise": ("hr", "symptom"),
     "cabin_trigger": ("symptom",),
+    # D45: opened only by hub/signals/trigger.py, always with the signal snapshot as `trigger`.
+    "signal_cabin": ("symptom",),
+    "signal_body": ("symptom", "mood"),
 }
+SIGNAL_KINDS = frozenset({"signal_cabin", "signal_body"})
 
 _SCHEMA = """
 CREATE TABLE IF NOT EXISTS prompts (
@@ -126,12 +130,14 @@
         *,
         trigger_reading_id: int | None = None,
         rule_id: str | None = None,
+        trigger: dict | None = None,
     ) -> Prompt:
         if kind not in PROMPT_ASKS:
             raise PromptError("bad_value:kind")
+        if (kind in SIGNAL_KINDS) != (trigger is not None):
+            raise PromptError("bad_value:kind")  # signal prompts come only from the trigger
         if crew is not None and crew not in CREWS:
             raise PromptError("bad_crew")
-        trigger = None
         if trigger_reading_id is not None:
             r = self.store.get_reading(trigger_reading_id)
             if r is not None:
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/test_prompts.py
```

Expected:

```text
8 passed, 1 warning
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/prompts.py hub/tests/test_prompts.py
git commit -m "feat(prompts): signal_cabin and signal_body kinds, created only with a snapshot"
```

### Task 14: The self-check trigger

Every 5 minutes, evaluate the six ★ signals; log each state change in `signal_events`; open a self-check only on `steady` → `notable`, never for a replay signal, not while one is open, and not inside the cooldown (2 h cabin, 24 h body). Never an alert.

**Files:**
- Create: `hub/signals/trigger.py`
- Create: `hub/tests/signals/test_trigger.py`
- Modify: `hub/features.py`

**Interfaces:**
- Consumes: Task 13's prompt kinds; Task 2's `evaluate`; `FeatureRuntime.start/stop`.
- Produces: `hub/signals/trigger.py` with `SignalTrigger(store, rules, prompts, *, crews, tz, clock)`, `.step(signal, now)`, `.tick(now=None) -> list[Prompt]`, `.period_s`, `TRIGGER_IDS`, `COOLDOWN`, `PERIOD_S = 300`, `snapshot(signal, at)`, `kind_for(signal)`; table `signal_events(id, signal_id, crew, state, at, prompt_id, snapshot)`; `FeatureRuntime.signals_trigger` and the `_run_trigger` loop.

- [ ] **Step 1: Write the failing test**

Create `hub/tests/signals/test_trigger.py`:

```python
from dataclasses import replace
from datetime import timedelta

import pytest

from hub.config import load_settings
from hub.prompts import PromptError, PromptService
from hub.signals.trigger import SignalTrigger
from hub.signals.types import Method, Signal, Value
from hub.tests.helpers import Rig, T


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


@pytest.fixture
def prompts(rig, clock):
    return PromptService(rig.store, rig.ing, load_settings({}), clock)


@pytest.fixture
def trig(rig, prompts, clock):
    return SignalTrigger(rig.store, [], prompts, crews=["crew-a"], tz="UTC", clock=clock)


M0 = Method("own_baseline", "ref", None, 7, 7, "a", "b", None)


def sig(state, crew="crew-a", sid="rest_hr_baseline", replay=False):
    v = Value(66, 55, 60, "bpm") if state != "not_enough_data" else None
    return Signal(sid, "baseline", crew, state, "signals.baseline.above", v, M0, replay=replay,
                  can_trigger=True)  # fmt: skip


def events(rig):
    with rig.store.lock:
        return rig.store.conn.execute(
            "SELECT signal_id, crew, state, prompt_id FROM signal_events ORDER BY id"
        ).fetchall()


def test_steady_to_notable_opens_one_body_prompt(trig, rig, prompts):
    assert trig.step(sig("steady"), T) is None
    p = trig.step(sig("notable"), T + timedelta(minutes=5))
    assert p.kind == "signal_body" and p.asks == ["symptom", "mood"] and p.crew == "crew-a"
    assert p.trigger["signal_id"] == "rest_hr_baseline" and p.trigger["value"]["estimate"] == 66
    assert "series" not in p.trigger
    assert trig.step(sig("notable"), T + timedelta(minutes=10)) is None  # no change, no event
    assert [e[2] for e in events(rig)] == ["steady", "notable"]


def test_first_data_straight_to_notable_opens_nothing(trig, rig):
    assert trig.step(sig("not_enough_data"), T) is None
    assert trig.step(sig("notable"), T + timedelta(minutes=5)) is None
    assert [e[3] for e in events(rig)] == [None, None]


def test_open_prompt_and_cooldown_block_a_second_prompt(trig, prompts, clock):
    trig.step(sig("steady"), T)
    first = trig.step(sig("notable"), T)
    trig.step(sig("steady"), T + timedelta(hours=1))
    assert trig.step(sig("notable"), T + timedelta(hours=2)) is None  # still open
    prompts.answer(first.id, [], skipped=True)
    trig.step(sig("steady"), T + timedelta(hours=3))
    assert trig.step(sig("notable"), T + timedelta(hours=4)) is None  # 24 h cooldown
    trig.step(sig("steady"), T + timedelta(hours=25))
    assert trig.step(sig("notable"), T + timedelta(hours=26)) is not None


def test_cabin_signal_opens_cabin_prompt_with_2h_cooldown(trig, prompts):
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T)
    p = trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"), T)
    assert p.kind == "signal_cabin" and p.asks == ["symptom"] and p.crew is None
    prompts.answer(p.id, [], skipped=True)
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=1))
    assert trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=1)) is None
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=2, minutes=1))
    assert trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"),
                     T + timedelta(hours=2, minutes=5)) is not None  # fmt: skip


def test_replay_signals_never_open_a_prompt(trig, rig):
    trig.step(sig("steady", replay=True), T)
    assert trig.step(sig("notable", replay=True), T) is None
    assert [e[2] for e in events(rig)] == ["steady", "notable"]


def test_never_an_alert(trig, rig):
    trig.step(sig("steady"), T)
    trig.step(sig("notable"), T)
    assert rig.alerts == [] and rig.store.count("outbox") == 0


def test_answer_payload_carries_no_signal_values(trig, rig, prompts):
    trig.step(sig("steady"), T)
    p = trig.step(sig("notable"), T)
    prompts.answer(p.id, [], skipped=True)
    [item] = rig.store.outbox_after(0, 10)
    assert item.kind == "prompt_answer" and item.payload["prompt_kind"] == "signal_body"
    assert item.payload["rule_id"] is None and "trigger" not in item.payload
    assert "66" not in str(item.payload)


def test_signal_kinds_cannot_be_opened_by_hand(prompts):
    with pytest.raises(PromptError):
        prompts.create("signal_body", "crew-a")
    with pytest.raises(PromptError):
        prompts.create("morning", "crew-a", trigger={"x": 1})


def test_tick_evaluates_trigger_signals_only(trig):
    assert trig.tick(T) == []  # an empty hub: everything is not_enough_data


def test_signals_feature_builds_the_trigger(settings, clock):
    from fastapi.testclient import TestClient

    from hub.api import create_app

    app = create_app(replace(settings, features=frozenset({"signals"})), clock=clock)
    with TestClient(app):
        assert app.state.runtime.signals_trigger is not None
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
python -m pytest -q hub/tests/signals/test_trigger.py
```

Expected (first error and summary):

```text
E   ModuleNotFoundError: No module named 'hub.signals.trigger'
1 error in 0.18s
```

- [ ] **Step 3: Write the implementation**

Create `hub/signals/trigger.py`:

```python
"""The self-check trigger (D45 §8). A notable signal may open a prompt; it never raises an alert.

Every state change of a ★ signal is logged in signal_events. A prompt opens only on a change from
`steady` to `notable`, when no prompt for that signal and crew is open, after the cooldown, and
never for a replay signal (synthetic data does not ask a real crew how they feel).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from hub.signals.catalogue import CATALOGUE
from hub.signals.engine import evaluate
from hub.signals.types import Signal
from hub.store import Store
from hub.thresholds import Rule
from hub.timeutil import parse_iso, to_iso

log = logging.getLogger("hub.signals.trigger")

TRIGGER_IDS: tuple[str, ...] = tuple(s.id for s in CATALOGUE if s.can_trigger)
COOLDOWN = {"signal_cabin": timedelta(hours=2), "signal_body": timedelta(hours=24)}
PERIOD_S = 300

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT NOT NULL, crew TEXT, state TEXT NOT NULL,
  at TEXT NOT NULL, prompt_id INTEGER, snapshot TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS signal_events_key ON signal_events(signal_id, crew, id);
"""


def kind_for(s: Signal) -> str:
    return "signal_cabin" if s.crew is None else "signal_body"


def snapshot(s: Signal, at: datetime) -> dict:
    """What the console shows next to the self-check: no series, no pairs."""
    d = s.to_dict()
    return {
        "signal_id": s.id, "state": s.state, "headline_key": s.headline_key, "value": d["value"],
        "inputs": d["inputs"], "limits": d["limits"], "reference": d["reference"],
        "replay": s.replay, "at": to_iso(at),
    }  # fmt: skip


class SignalTrigger:
    def __init__(
        self, store: Store, rules: Sequence[Rule], prompts, *, crews: Sequence[str], tz: str,
        clock: Callable[[], datetime],
    ) -> None:  # fmt: skip
        self.store, self.rules, self.prompts = store, rules, prompts
        self.crews, self.tz, self.clock = list(crews), tz, clock
        self.period_s = PERIOD_S
        with store.lock:
            store.conn.executescript(_SCHEMA)
            store.conn.commit()

    def _last(self, signal_id: str, crew: str | None, with_prompt: bool = False) -> tuple | None:
        sql = "SELECT state, at, prompt_id FROM signal_events WHERE signal_id=?"
        args: list = [signal_id]
        sql += " AND crew IS NULL" if crew is None else " AND crew=?"
        if crew is not None:
            args.append(crew)
        if with_prompt:
            sql += " AND prompt_id IS NOT NULL"
        sql += " ORDER BY id DESC LIMIT 1"
        with self.store.lock:
            return self.store.conn.execute(sql, args).fetchone()

    def _log(self, s: Signal, at: datetime, prompt_id: int | None, snap: dict) -> None:
        with self.store.lock:
            self.store.conn.execute(
                "INSERT INTO signal_events (signal_id, crew, state, at, prompt_id, snapshot)"
                " VALUES (?,?,?,?,?,?)",
                (s.id, s.crew, s.state, to_iso(at), prompt_id, json.dumps(snap)),
            )
            self.store.conn.commit()

    def _open_for(self, s: Signal) -> bool:
        for p in self.prompts.pending(s.crew):
            if (
                p.crew == s.crew
                and p.kind == kind_for(s)
                and (p.trigger or {}).get("signal_id") == s.id
            ):
                return True
        return False

    def _cooling(self, s: Signal, now: datetime) -> bool:
        last = self._last(s.id, s.crew, with_prompt=True)
        return last is not None and now - parse_iso(last[1]) < COOLDOWN[kind_for(s)]

    def step(self, s: Signal, now: datetime):
        """Log a state change and maybe open a prompt; returns the prompt or None."""
        last = self._last(s.id, s.crew)
        prev = last[0] if last else None
        if prev == s.state:
            return None
        snap = snapshot(s, now)
        prompt = None
        if (s.state == "notable" and prev == "steady" and not s.replay
                and not self._open_for(s) and not self._cooling(s, now)):  # fmt: skip
            prompt = self.prompts.create(kind_for(s), s.crew, trigger=snap)
        self._log(s, now, prompt.id if prompt else None, snap)
        return prompt

    def tick(self, now: datetime | None = None) -> list:
        now = now or self.clock()
        out = []
        for s in evaluate(self.store, self.rules, crews=self.crews, at=now, tz=self.tz,
                          ids=TRIGGER_IDS):  # fmt: skip
            try:
                p = self.step(s, now)
            except Exception:
                log.exception("signal trigger failed for %s %s", s.id, s.crew)
                continue
            if p is not None:
                out.append(p)
        return out
```

Modify `hub/features.py`:

```diff
--- a/hub/features.py
+++ b/hub/features.py
@@ -7,6 +7,7 @@
 from __future__ import annotations
 
 import asyncio
+import contextlib
 import importlib
 import inspect
 import logging
@@ -72,6 +73,7 @@
     "signals": {
         "hub.signals.engine": ("evaluate",),
         "hub.signals.routes": ("router", "SignalsState"),
+        "hub.signals.trigger": ("SignalTrigger",),
     },
 }
 
@@ -119,12 +121,14 @@
     iss_client: Any | None = None
     mcp: Any | None = None
     wearable: Any | None = None
+    signals_trigger: Any | None = None
     badge_handlers: list[Callable[[str, str, datetime], object]] = field(default_factory=list)
     _poller: Any | None = None  # (coroutine factory) built by wire_features
     _client: httpx.AsyncClient | None = None
     _task: asyncio.Task | None = None
     _stop: asyncio.Event | None = None
     _stack: AsyncExitStack | None = None
+    _trigger_task: asyncio.Task | None = None
 
     async def start(self, stop: asyncio.Event) -> None:
         self._stop = stop
@@ -141,6 +145,8 @@
                     await r
             except Exception:
                 log.exception("iss client failed to start")
+        if self.signals_trigger is not None:
+            self._trigger_task = asyncio.create_task(_run_trigger(self.signals_trigger, stop))
         if self.mcp is not None:
             self._stack = AsyncExitStack()
             try:
@@ -150,6 +156,10 @@
                 self._stack = None
 
     async def stop(self) -> None:
+        if self._trigger_task is not None:
+            self._trigger_task.cancel()
+            with contextlib.suppress(asyncio.CancelledError, Exception):
+                await self._trigger_task
         if self._stack is not None:
             try:
                 await self._stack.aclose()
@@ -175,6 +185,18 @@
                 await self._client.aclose()
             except Exception:
                 log.exception("http client failed to close")
+
+
+async def _run_trigger(trigger: Any, stop: asyncio.Event) -> None:
+    """The signals self-check loop (D45 §8): one tick every period_s, errors logged and survived."""
+    period = getattr(trigger, "period_s", 300)
+    while not stop.is_set():
+        try:
+            await asyncio.to_thread(trigger.tick)
+        except Exception:
+            log.exception("signals trigger tick failed")
+        with contextlib.suppress(TimeoutError):
+            await asyncio.wait_for(stop.wait(), timeout=period)
 
 
 def _guard(
@@ -305,6 +327,12 @@
             ctx.store, ctx.assessor.rules, crews, settings.tz, ctx.clock
         )
         app.include_router(routes.router)
+        prompts = getattr(app.state, "prompts", None)
+        if prompts is not None:
+            rt.signals_trigger = f.mod("hub.signals.trigger").SignalTrigger(
+                ctx.store, ctx.assessor.rules, prompts, crews=crews, tz=settings.tz,
+                clock=ctx.clock,
+            )  # fmt: skip
 
     if "signals" in on and "signals" not in f.skipped:
         _guard(f, "signals", build_signals)
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
python -m pytest -q hub/tests/signals/test_trigger.py
```

Expected:

```text
10 passed, 1 warning
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
ruff check hub nodes && ruff format --check hub/signals hub/tests/signals nodes/weather hub/nasa/iss_store.py
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add hub/features.py hub/signals/trigger.py hub/tests/signals/test_trigger.py
git commit -m "feat(signals): self-check trigger with signal_events (never an alert)"
```

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat(signals): D45 self-check trigger" --body "Implements D45 slice 5 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 13–14."
```

---

## Slice 6: the console (PR 6)

Branch `feat/d45-signals-console`. The `#/signals` screen and the panel's chip. Rebuild the console after it
(`npm --prefix console run build`) so the hub serves the new bundle.

### Task 15: Console: signal types, copy, wording model and the prediction lint

The console side of the contract, every signal word, the pure wording model, and the `rulePrediction` honesty rule run over all signal copy.

**Files:**
- Create: `console/src/model/signals.ts`
- Create: `console/tests/signals.test.ts`
- Modify: `console/src/contract.ts`
- Modify: `console/src/api.ts`
- Modify: `console/src/copy.ts`
- Modify: `console/tests/honesty.ts`
- Modify: `console/tests/copy.test.ts`

**Interfaces:**
- Consumes: the `/api/signals` body (Task 3) and the prompt `trigger` snapshot (Task 14).
- Produces: `contract.ts` types `Signal`, `SignalValue`, `SignalMethod`, `SignalMissing`, `SignalInput`, `SignalsBody`, `SignalSnapshot`, `SignalKind`, `SignalState`; `SrcClass` gains `"ref"`; `Prompt.kind` gains the two signal kinds; `api.ts` `getSignals(crew?, at?)`; `model/signals.ts` `GROUPS`, `groupOf`, `fmt`, `unitLabel`, `headline`, `missingLines`, `limitLines`, `lagLines`, `notableCount`, `selfCheckFor`, `sparkValues`; `tests/honesty.ts` `rulePrediction`.

- [ ] **Step 1: Write the failing tests**

Create `console/tests/signals.test.ts`:

```ts
// D45 signals: the wording model and the screen's cards, from hub-shaped signal objects.
import { describe, expect, test } from "vitest";
import type { Prompt, Signal, SignalsBody } from "../src/contract";
import { fmt, groupOf, headline, lagLines, missingLines, notableCount, selfCheckFor } from "../src/model/signals";

const NOW = Date.parse("2026-11-20T10:00:00Z");

const sig = (over: Partial<Signal> = {}): Signal => ({
  id: "rest_hr_baseline", kind: "baseline", crew: "crew-a", state: "steady",
  headline_key: "signals.baseline.inside", value: { estimate: 57, low: 54.03, high: 59.97, unit: "bpm", per: null },
  method: { name: "own_baseline", ref: "median and MAD", alpha: null, n: 14, min_n: 7,
    window_start: "2026-11-06T10:00:00.000Z", window_end: "2026-11-20T10:00:00.000Z", coverage: null },
  inputs: [{ ind: "hr", src: "hobby", dev: "RING", node: "ring-1", n: 1000, first_at: "2026-11-06T03:00:00.000Z",
    last_at: "2026-11-20T09:00:00.000Z", oldest_age_s: 3600 }],
  missing: [], limits: ["signals.limit.ringEstimate"], reference: null, replay: false,
  series: [["2026-11-18T10:00:00.000Z", 56], ["2026-11-19T10:00:00.000Z", 57], ["2026-11-20T10:00:00.000Z", 57]],
  pairs: [], can_trigger: true, detail: {}, ...over,
});

describe("signals model", () => {
  test("baseline, trend, time-to-limit and missing wording", () => {
    expect(headline(sig())).toBe("Inside your own usual range: 57.0 bpm (usual 54.0 to 60.0).");
    expect(headline(sig({ kind: "trend", headline_key: "signals.trend.up",
      value: { estimate: 0.5, low: 0.31, high: 0.72, unit: "C", per: "h" } })))
      .toBe("Trend up: 0.50 °C per hour (interval 0.31 to 0.72).");
    expect(headline(sig({ id: "cabin_rh_ttl", kind: "time_to_limit", crew: null, headline_key: "signals.ttl.reaches",
      value: { estimate: 3.8, low: 3.4, high: 4.3, unit: "h", per: null },
      reference: { rule_id: "cabin_health_box_rh", source_kind: "nasa_std", limit: 75 },
      inputs: [{ ...sig().inputs[0], ind: "cabin_rh" }] })))
      .toBe("At this rate, reaches 75.0 % in 3.40 to 4.30 h, if nothing changes.");
    const nd = sig({ state: "not_enough_data", headline_key: "signals.nodata", value: null,
      missing: [{ key: "signals.missing.priorDays", need: 7, have: 4 }] });
    expect(headline(nd)).toBe("Not enough data yet.");
    expect(missingLines(nd)).toEqual(["Needs 7 earlier days for your usual range; has 4."]);
  });

  test("lag lines name every lag and pick none", () => {
    const s = sig({ id: "cabin_vs_earth", kind: "lagged_pair", crew: null, value: null, headline_key: "signals.pair.rho",
      detail: { lags: [{ lag_h: 0, n: 30, rho: 0.41, low: 0.06, high: 0.67 }, { lag_h: 1, n: 5, rho: null, low: null, high: null }] } });
    expect(lagLines(s)).toEqual([
      "0 h later: 30 pairs, rank correlation 0.41 (interval 0.06 to 0.67).",
      "1 h later: 5 pairs, too few to say anything.",
    ]);
  });

  test("groups, number format, notable count, open self-check", () => {
    expect(groupOf("cabin_rh_ttl")).toBe("cabin");
    expect(groupOf("water_14d")).toBe("food");
    expect(fmt(-0.123)).toBe("−0.12");
    const body: SignalsBody = { crew: null, at: "x", signals: [sig({ state: "notable" }), sig()] };
    expect(notableCount(body)).toBe(1);
    expect(notableCount(null)).toBe(0);
    const p = { id: 9, kind: "signal_body", crew: "crew-a", status: "open", created_at: "x", asks: ["symptom", "mood"],
      trigger_reading_id: null, rule_id: null,
      trigger: { signal_id: "rest_hr_baseline", state: "notable", headline_key: "x", value: null, inputs: [], limits: [],
        reference: null, replay: false, at: "x" } } as Prompt;
    expect(selfCheckFor([p], sig())?.id).toBe(9);
    expect(selfCheckFor([p], sig({ crew: "crew-c" }))).toBeUndefined();
  });
});
```

Modify `console/tests/honesty.ts`:

```diff
--- a/console/tests/honesty.ts
+++ b/console/tests/honesty.ts
@@ -22,6 +22,10 @@
 
 export const ruleNonEnglish = (s: string): boolean => /[ãõçáéíóúâêôà]/i.test(s);
 
+// D45: signal wording never claims to foresee. "not a prediction" is the one allowed use.
+export const rulePrediction = (s: string): boolean =>
+  /\bpredict\w*|\bforecast\w*|\brisk\b|\bwill\b/i.test(s.replace(/not a prediction/gi, ""));
+
 export const ruleCameraWording = (s: string): boolean => /measured|validated|accurate/i.test(s);
 
 // Extract string literals from TypeScript source text (single, double, template). Skips comments.
```

Modify `console/tests/copy.test.ts`:

```diff
--- a/console/tests/copy.test.ts
+++ b/console/tests/copy.test.ts
@@ -4,7 +4,7 @@
 import { COPY, DISCLAIMER } from "../src/copy";
 import {
   ruleBrand, ruleCalories, ruleCameraWording, ruleDiagnosis, ruleEnergyBalance, ruleMealPlan, ruleNonEnglish,
-  ruleTreatmentDose, stringLiterals,
+  rulePrediction, ruleTreatmentDose, stringLiterals,
 } from "./honesty";
 
 const ROOT = join(__dirname, "..");
@@ -55,6 +55,18 @@
   items.filter((w) => rule(w.text)).map((w) => `${w.where}: ${w.text}`);
 
 describe("honesty lint", () => {
+  test("test_signals_wording (D45)", () => {
+    for (const s of ["predicted rise", "Forecast", "heart risk", "It will reach"]) expect(rulePrediction(s)).toBe(true);
+    for (const s of ["Logged trend extended, arithmetic only, not a prediction", "At this rate", "willing"]) {
+      expect(rulePrediction(s)).toBe(false);
+    }
+    const signalTexts = ALL.filter((w) => w.where.startsWith("COPY.signals.") || w.where === "src/views/signals.ts"
+      || w.where === "COPY.panel.chipSignals" || w.where === "COPY.panel.signalsNotable");
+    expect(signalTexts.length).toBeGreaterThan(60);
+    expect(bad(rulePrediction, signalTexts)).toEqual([]);
+    expect(bad(ruleCameraWording, signalTexts)).toEqual([]);
+  });
+
   test("self-check: rules catch the fixed samples", () => {
     for (const s of ["300 kcal", "Calories burned", "calorie"]) expect(ruleCalories(s)).toBe(true);
     for (const s of ["Calibrate the scale", "Work is mechanical work in joules, not food energy."]) {
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
npm --prefix console test -- tests/signals.test.ts tests/honesty.ts tests/copy.test.ts
```

Expected (first error and summary):

```text
Error: Cannot find module '../src/model/signals' imported from console/tests/signals.test.ts
Tests  1 failed | 12 passed (13)
```

- [ ] **Step 3: Write the implementation**

Create `console/src/model/signals.ts`:

```ts
// Signals (D45): pure wording of the hub's signal objects. Every word comes from COPY; the hub sends keys and numbers.
import { COPY } from "../copy";
import type { Prompt, Signal, SignalSnapshot, SignalsBody } from "../contract";
import { UNITS } from "../payload";

export type SignalGroup = "cabin" | "body" | "food" | "lift" | "cross";
export const GROUPS: SignalGroup[] = ["cabin", "body", "food", "lift", "cross"];

const GROUP_OF: Record<string, SignalGroup> = {
  cabin_temp_6h: "cabin", cabin_rh_6h: "cabin", cabin_temp_ttl: "cabin", cabin_rh_ttl: "cabin",
  cabin_ppco2_ttl: "cabin", iss_ppco2_6h: "cabin",
  rest_hr_baseline: "body", rest_hr_14n: "body", sleep_baseline: "body", spo2_baseline: "body",
  body_mass_30d: "food", water_14d: "food",
  lift_work_sets: "lift", lift_within_set: "lift", lift_tilt_agreement: "lift",
  cabin_vs_earth: "cross", training_vs_rest_hr: "cross", last_meal_vs_sleep: "cross", space_weather_vs_sleep: "cross",
};

export function groupOf(id: string): SignalGroup {
  return GROUP_OF[id] ?? "cross";
}

/** Two decimals under 10, one decimal above: the interval is the honest part, not the digits. */
export function fmt(x: number): string {
  const r = Math.abs(x) < 10 ? x.toFixed(2) : x.toFixed(1);
  return r.replace(/^-/, "−");
}

export function unitLabel(unit: string): string {
  if (unit === "C") return "°C";
  if (unit === "rho" || unit === "h") return unit === "h" ? "h" : "";
  return COPY[`signals.unit.${unit}`] ?? unit;
}

const fill = (t: string, v: Record<string, string | number>) =>
  Object.entries(v).reduce((s, [k, x]) => s.split(`{${k}}`).join(String(x)), t);

/** The card's headline sentence. */
export function headline(s: Signal | SignalSnapshot): string {
  const t = COPY[s.headline_key] ?? COPY["signals.nodata"];
  const v = s.value;
  const n = "method" in s ? s.method.n : 0;
  if (s.headline_key === "signals.ttl.reaches" && v) {
    const ind = s.inputs[0]?.ind;
    const unit = unitLabel((ind && (UNITS as Record<string, string>)[ind]) || "");
    return fill(t, { limit: fmt(s.reference?.limit ?? 0), unit, low: fmt(v.low), high: fmt(v.high) });
  }
  if (!v) return fill(t, { n });
  return fill(t, {
    est: fmt(v.estimate), low: fmt(v.low), high: fmt(v.high), unit: unitLabel(v.unit),
    per: v.per ? COPY[`signals.per.${v.per}`] ?? v.per : "", n,
  }).replace(/ {2,}/g, " ");
}

export function missingLines(s: Signal): string[] {
  return s.missing.map((m) => fill(COPY[m.key] ?? COPY["signals.nodata"], { need: m.need ?? "", have: m.have ?? "" }));
}

export function limitLines(s: Signal | SignalSnapshot): string[] {
  return s.limits.map((k) => COPY[k]).filter((x): x is string => typeof x === "string");
}

/** One line per lag for cabin_vs_earth (no lag is picked as the best one). */
export function lagLines(s: Signal): string[] {
  const lags = (s.detail.lags ?? []) as { lag_h: number; n: number; rho: number | null; low: number | null; high: number | null }[];
  return lags.map((l) =>
    l.rho === null || l.low === null || l.high === null
      ? fill(COPY["signals.pair.lagFew"], { h: l.lag_h, n: l.n })
      : fill(COPY["signals.pair.lag"], { h: l.lag_h, n: l.n, rho: fmt(l.rho), low: fmt(l.low), high: fmt(l.high) }),
  );
}

export function notableCount(body: SignalsBody | null): number {
  return (body?.signals ?? []).filter((s) => s.state === "notable").length;
}

/** The open self-check prompt this signal opened, if any. */
export function selfCheckFor(prompts: Prompt[], s: Signal): Prompt | undefined {
  return prompts.find((p) => p.status === "open" && p.crew === s.crew
    && (p.kind === "signal_cabin" || p.kind === "signal_body")
    && (p.trigger as SignalSnapshot | null)?.signal_id === s.id);
}

/** Numbers of a series for a sparkline, in order; [time or rep, value] pairs from the hub. */
export function sparkValues(s: Signal): number[] {
  return s.series.map((p) => p[1]).filter((x) => Number.isFinite(x));
}
```

Modify `console/src/contract.ts`:

```diff
--- a/console/src/contract.ts
+++ b/console/src/contract.ts
@@ -39,7 +39,7 @@
   | "body_mass"
   | IntakeInd;
 
-export type SrcClass = "certified" | "hobby" | "self" | "nasa" | "replay";
+export type SrcClass = "certified" | "hobby" | "self" | "nasa" | "replay" | "ref";
 export type QualityFlag =
   | "ok"
   | "motion"
@@ -183,14 +183,14 @@
 
 export interface Prompt {
   id: number;
-  kind: "morning" | "post_exercise" | "cabin_trigger";
+  kind: "morning" | "post_exercise" | "cabin_trigger" | "signal_cabin" | "signal_body";
   asks: Ind[];
   crew: CrewId | null;
   status: "open" | "answered" | "skipped";
   created_at: string;
   trigger_reading_id: number | null;
   rule_id: string | null;
-  trigger: StatusEntry | null;
+  trigger: StatusEntry | SignalSnapshot | null;
 }
 
 export interface PromptAnswer {
@@ -401,4 +401,82 @@
   cell_work_j: number | null;
   replay: boolean;
   excluded_reps: number;
+}
+
+// Signals (D45). The hub sends keys, never text: the console words them from COPY.
+export type SignalKind = "trend" | "baseline" | "time_to_limit" | "lagged_pair";
+export type SignalState = "notable" | "steady" | "not_enough_data";
+
+export interface SignalInput {
+  ind: string;
+  src: SrcClass;
+  dev: string;
+  node: string;
+  n: number;
+  first_at: string;
+  last_at: string;
+  oldest_age_s: number;
+}
+
+export interface SignalValue {
+  estimate: number;
+  low: number;
+  high: number;
+  unit: string;
+  per: string | null;
+}
+
+export interface SignalMethod {
+  name: string;
+  ref: string;
+  alpha: number | null;
+  n: number;
+  min_n: number;
+  window_start: string;
+  window_end: string;
+  coverage: number | null;
+}
+
+export interface SignalMissing {
+  key: string;
+  need: number | null;
+  have: number | null;
 }
+
+export interface Signal {
+  id: string;
+  kind: SignalKind;
+  crew: CrewId | null;
+  state: SignalState;
+  headline_key: string;
+  value: SignalValue | null;
+  method: SignalMethod;
+  inputs: SignalInput[];
+  missing: SignalMissing[];
+  limits: string[];
+  reference: { rule_id: string; source_kind: SourceKind; limit: number | null } | null;
+  replay: boolean;
+  series: [string | number, number][];
+  pairs: (string | number)[][];
+  can_trigger: boolean;
+  detail: Record<string, unknown>;
+}
+
+export interface SignalsBody {
+  crew: CrewId | null;
+  at: string;
+  signals: Signal[];
+}
+
+/** The `trigger` of a signal_cabin / signal_body prompt: what the signal showed when it asked. */
+export interface SignalSnapshot {
+  signal_id: string;
+  state: SignalState;
+  headline_key: string;
+  value: SignalValue | null;
+  inputs: SignalInput[];
+  limits: string[];
+  reference: Signal["reference"];
+  replay: boolean;
+  at: string;
+}
```

Modify `console/src/api.ts`:

```diff
--- a/console/src/api.ts
+++ b/console/src/api.ts
@@ -1,7 +1,7 @@
 import type {
   CrewId, ExerciseDay, FoodCatalog, FoodDay, FoodReferences, Ind, IssCabin, IssReference, LinkState, MealRequest,
-  MealResult, PostResult, Prompt, PromptAnswer, PromptAnswerResult, ReadingMessage, RepsBody, Session, SpaceWeather,
-  StatusBody, StoredReading,
+  MealResult, PostResult, Prompt, PromptAnswer, PromptAnswerResult, ReadingMessage, RepsBody, Session, SignalsBody,
+  SpaceWeather, StatusBody, StoredReading,
 } from "./contract";
 
 export class ApiError extends Error {
@@ -152,6 +152,10 @@
   return guard("/api/food/day", await get("/api/food/day", { crew, at }), (o) => typeof o.totals === "object" && o.totals !== null);
 }
 
+export async function getSignals(crew?: CrewId, at?: string): Promise<SignalsBody> {
+  return guard("/api/signals", await get("/api/signals", { crew, at }), (o) => Array.isArray(o.signals));
+}
+
 export async function getExerciseDay(crew?: CrewId, at?: string): Promise<ExerciseDay> {
   return guard("/api/exercise/day", await get("/api/exercise/day", { crew, at }), (o) => typeof o.sessions === "number");
 }
```

Modify `console/src/copy.ts`:

```diff
--- a/console/src/copy.ts
+++ b/console/src/copy.ts
@@ -315,6 +315,88 @@
   "panel.notInReplay": "Not in this replay:",
   "panel.notInReplayShort": "not in this replay",
   "panel.massNoneReplay": "No weigh-ins in this replay.",
+  // Signals (D45). Wording is fixed per kind: "trend", "own usual range", "at this rate", "side by side".
+  "nav.signals": "Signals",
+  "src.ref": "Earth reference, outdoor",
+  "panel.chipSignals": "Signals",
+  "panel.signalsNotable": "{n} notable",
+  "signals.intro": "Labelled trends and side-by-side views of the habitat's own data. Each card shows its inputs, method and limits.",
+  "signals.group.cabin": "Cabin",
+  "signals.group.body": "Body",
+  "signals.group.food": "Food and body mass",
+  "signals.group.lift": "Lift",
+  "signals.group.cross": "Side by side",
+  "signals.state.notable": "Notable",
+  "signals.state.steady": "Steady",
+  "signals.state.not_enough_data": "Not enough data yet",
+  "signals.method": "How this is worked out",
+  "signals.window": "{n} points, {from} to {to}",
+  "signals.selfCheck": "A self-check is open for this signal.",
+  "signals.none": "No signals: the signals feature is off on this hub.",
+  "signals.title.cabin_temp_6h": "Cabin temperature, last 6 hours",
+  "signals.title.cabin_rh_6h": "Cabin humidity, last 6 hours",
+  "signals.title.cabin_temp_ttl": "Cabin temperature and its NASA limit",
+  "signals.title.cabin_rh_ttl": "Cabin humidity and its NASA limit",
+  "signals.title.cabin_ppco2_ttl": "Cabin ppCO2 (1-hour mean) and its NASA limit",
+  "signals.title.iss_ppco2_6h": "ISS ppCO2, last 6 hours",
+  "signals.title.cabin_vs_earth": "Bench cabin and outdoor temperature",
+  "signals.title.rest_hr_baseline": "Resting heart rate last night",
+  "signals.title.rest_hr_14n": "Resting heart rate, 14 nights",
+  "signals.title.sleep_baseline": "Sleep last night",
+  "signals.title.spo2_baseline": "SpO2 last night",
+  "signals.title.body_mass_30d": "Body mass, 30 days",
+  "signals.title.water_14d": "Water logged, 14 days",
+  "signals.title.lift_work_sets": "Work per rep across your sets",
+  "signals.title.lift_within_set": "Work per rep in your latest set",
+  "signals.title.lift_tilt_agreement": "Camera and tilt switch agreement",
+  "signals.title.training_vs_rest_hr": "Training work and that night's resting heart rate",
+  "signals.title.last_meal_vs_sleep": "Last meal time and that night's sleep",
+  "signals.title.space_weather_vs_sleep": "Space weather and that night's sleep",
+  "signals.trend.up": "Trend up: {est} {unit} per {per} (interval {low} to {high}).",
+  "signals.trend.down": "Trend down: {est} {unit} per {per} (interval {low} to {high}).",
+  "signals.trend.flat": "No clear trend: {est} {unit} per {per} (interval {low} to {high}).",
+  "signals.ttl.reaches": "At this rate, reaches {limit} {unit} in {low} to {high} h, if nothing changes.",
+  "signals.ttl.none": "At this rate, not near a limit within 12 hours.",
+  "signals.ttl.away": "Moving away from the limit.",
+  "signals.ttl.outside": "Already outside the limit: the status board shows it.",
+  "signals.baseline.above": "Above your own usual range: {est} {unit} (usual {low} to {high}).",
+  "signals.baseline.below": "Below your own usual range: {est} {unit} (usual {low} to {high}).",
+  "signals.baseline.inside": "Inside your own usual range: {est} {unit} (usual {low} to {high}).",
+  "signals.pair.few": "Side by side: {n} pairs, too few pairs to say anything.",
+  "signals.pair.rho": "Side by side: rank correlation {est} (interval {low} to {high}), {n} pairs. Association in your own data, not cause.",
+  "signals.pair.lag": "{h} h later: {n} pairs, rank correlation {rho} (interval {low} to {high}).",
+  "signals.pair.lagFew": "{h} h later: {n} pairs, too few to say anything.",
+  "signals.pair.noBest": "No lag is picked as the best one.",
+  "signals.nodata": "Not enough data yet.",
+  "signals.missing.blocks": "Needs {need} time blocks with data; has {have}.",
+  "signals.missing.nights": "Needs {need} nights; has {have}.",
+  "signals.missing.days": "Needs {need} days with a value; has {have}.",
+  "signals.missing.sets": "Needs {need} sets of one exercise; has {have}.",
+  "signals.missing.reps": "Needs {need} reps in the latest set; has {have}.",
+  "signals.missing.priorDays": "Needs {need} earlier days for your usual range; has {have}.",
+  "signals.missing.priorSets": "Needs {need} earlier sets for your usual range; has {have}.",
+  "signals.missing.spread": "Your earlier values are all the same, so there is no range yet.",
+  "signals.missing.recentNight": "No night recorded in the last 36 hours.",
+  "signals.missing.rule": "The limit rule is not loaded on this hub.",
+  "signals.missing.pairs": "No pairs yet: both sides are needed on the same days.",
+  "signals.limit.independence": "Assumes independent points. Blocking reduces serial correlation but does not remove it.",
+  "signals.limit.benchSensor": "Bench hobby sensor, not a certified device.",
+  "signals.limit.straightLine": "A straight-line extension of the last 2 hours. Opening a hatch, a person entering or the air system cycling changes it.",
+  "signals.limit.ringEstimate": "Consumer ring estimate from a delayed cloud sync. Not a medical device.",
+  "signals.limit.restOnly": "Heart-rate samples from rest and sleep only, one every 5 minutes.",
+  "signals.limit.ownData": "Your own data only, over a small number of days.",
+  "signals.limit.issTelemetry": "ISS public telemetry: the lab and Node 3 ppCO2 items together.",
+  "signals.limit.earthReference": "Earth reference, outdoor: the nearest public weather station's raw hourly data, not quality-checked by the weather service, and not the bench itself.",
+  "signals.limit.neighbourHours": "Hours next to each other are not independent, so the interval is too narrow.",
+  "signals.limit.cameraEstimate": "Camera estimate of work on the load, divided by g so sets at any gravity compare.",
+  "signals.limit.notFoodEnergy": "Mechanical work on the load. It is never compared with food energy.",
+  "signals.limit.rigCheck": "A check on the rig and camera timing, not on the crew.",
+  "signals.limit.onEarth": "The bench crew is on Earth, shielded by the atmosphere. This pairing shows the method, not an effect.",
+  "signals.limit.loggedOnly": "Only what was logged. A day without an entry has no value.",
+  "signals.unit.kg_m": "kg·m",
+  "signals.per.h": "hour",
+  "signals.per.day": "day",
+  "signals.per.rep": "rep",
 };
 
 export type CopyKey = keyof typeof COPY;
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
npm --prefix console test -- tests/signals.test.ts tests/honesty.ts tests/copy.test.ts
```

Expected:

```text
Tests  16 passed (16)
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
npm --prefix console run typecheck && npm --prefix console test
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add console/src/api.ts console/src/contract.ts console/src/copy.ts console/src/model/signals.ts console/tests/copy.test.ts console/tests/honesty.ts console/tests/signals.test.ts
git commit -m "feat(console): signal types, copy and wording model; prediction lint"
```

### Task 16: Console: the `#/signals` screen

One card per signal, grouped Cabin · Body · Food and body mass · Lift · Side by side. `not_enough_data` cards are greyed and say what is missing, never hidden. The sparkline is drawn from markup like the panel's link strip, so the offline-bundle scan finds no external host.

**Files:**
- Create: `console/src/views/signals.ts`
- Modify: `console/tests/signals.test.ts`
- Modify: `console/src/screens.ts`
- Modify: `console/src/main.ts`
- Modify: `console/tests/smoke.test.ts`
- Modify: `console/src/styles.css`

**Interfaces:**
- Consumes: Task 15's model and `getSignals`; `getPrompts`.
- Produces: `views/signals.ts` with `signalCard(s, prompts, now)`, `renderSignalsBody(root, body, prompts, now)`, `renderSignals(root) -> dispose`; screen id `"signals"` in `SCREENS` and its route in `main.ts`.

- [ ] **Step 1: Write the failing tests**

Modify `console/tests/signals.test.ts`:

```diff
--- a/console/tests/signals.test.ts
+++ b/console/tests/signals.test.ts
@@ -1,7 +1,9 @@
+// @vitest-environment jsdom
 // D45 signals: the wording model and the screen's cards, from hub-shaped signal objects.
 import { describe, expect, test } from "vitest";
 import type { Prompt, Signal, SignalsBody } from "../src/contract";
 import { fmt, groupOf, headline, lagLines, missingLines, notableCount, selfCheckFor } from "../src/model/signals";
+import { renderSignalsBody } from "../src/views/signals";
 
 const NOW = Date.parse("2026-11-20T10:00:00Z");
 
@@ -58,3 +60,31 @@
     expect(selfCheckFor([p], sig({ crew: "crew-c" }))).toBeUndefined();
   });
 });
+
+describe("signals screen", () => {
+  test("cards per group, not-enough-data greyed and shown, replay chips", () => {
+    const root = document.createElement("div");
+    const body: SignalsBody = { crew: "crew-a", at: "x", signals: [
+      sig({ state: "notable", headline_key: "signals.baseline.above", value: { estimate: 66, low: 54, high: 60, unit: "bpm", per: null } }),
+      sig({ id: "water_14d", state: "not_enough_data", headline_key: "signals.nodata", value: null,
+        missing: [{ key: "signals.missing.days", need: 11, have: 9 }], replay: true,
+        inputs: [{ ...sig().inputs[0], ind: "intake_water_ml", src: "replay", dev: "catalog" }] }),
+    ] };
+    renderSignalsBody(root, body, [], NOW);
+    const t = root.textContent ?? "";
+    expect(t).toContain("Body");
+    expect(t).toContain("Food and body mass");
+    expect(t).toContain("Above your own usual range: 66.0 bpm");
+    expect(t).toContain("Needs 11 days with a value; has 9.");
+    expect(t).toContain("Replay (recorded) · catalog");
+    expect(t).toContain("This is not a diagnosis.");
+    expect(root.querySelector('[data-signal="water_14d"]')?.classList.contains("greyed")).toBe(true);
+    expect(root.querySelector('[data-signal="rest_hr_baseline"]')?.classList.contains("watch")).toBe(true);
+  });
+
+  test("signals off on the hub", () => {
+    const root = document.createElement("div");
+    renderSignalsBody(root, null, [], NOW);
+    expect(root.textContent).toContain("the signals feature is off");
+  });
+});
```

Modify `console/tests/smoke.test.ts`:

```diff
--- a/console/tests/smoke.test.ts
+++ b/console/tests/smoke.test.ts
@@ -3,7 +3,7 @@
 
 describe("scaffold", () => {
   test("test_screens_list", () => {
-    expect([...SCREENS]).toEqual(["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "prompts", "body"]);
+    expect([...SCREENS]).toEqual(["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "signals", "prompts", "body"]);
   });
   test("test_default_screen", () => {
     expect(screenFromHash("")).toBe("panel");
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
npm --prefix console test -- tests/signals.test.ts tests/smoke.test.ts
```

Expected (first error and summary):

```text
Error: Failed to resolve import "../src/views/signals" from "tests/signals.test.ts". Does the file exist?
Tests  1 failed | 1 passed (2)
```

- [ ] **Step 3: Write the implementation**

Create `console/src/views/signals.ts`:

```ts
// The signals screen (D45 §9.1): one card per signal, grouped. Read-only: the screen never writes to the hub.
import { getPrompts, getSignals } from "../api";
import { COPY, DISCLAIMER } from "../copy";
import type { Prompt, Signal, SignalsBody } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { formatAge, srcLabel } from "../format";
import {
  GROUPS, groupOf, headline, lagLines, limitLines, missingLines, selfCheckFor, sparkValues,
} from "../model/signals";

const REFRESH_MS = 30_000;
/** A sparkline drawn from markup, as the panel's link strip is (numbers only go into it). */
function spark(values: number[]): HTMLElement | null {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * 100).toFixed(1)},${(28 - ((v - lo) / span) * 24).toFixed(1)}`);
  const box = el("div", { class: "spark", "aria-hidden": "true" });
  box.innerHTML = `<svg viewBox="0 0 100 30" preserveAspectRatio="none"><polyline points="${pts.join(" ")}"/></svg>`;
  return box;
}

function chips(s: Signal, now: number): HTMLElement {
  const out = el("div", {});
  for (const i of s.inputs) {
    const age = formatAge(Math.max(0, (now - Date.parse(i.last_at)) / 1000));
    out.append(el("span", { class: s.replay ? "chip estimate" : "chip", text: `${srcLabel(i.src)} · ${i.dev} · ${age}` }));
  }
  return out;
}

export function signalCard(s: Signal, prompts: Prompt[], now: number): HTMLElement {
  const cls = s.state === "notable" ? "watch" : s.state === "steady" ? "ok" : "greyed";
  const how = el("details", {},
    el("summary", { text: COPY["signals.method"] }),
    el("div", { class: "footnote", text: `${s.method.name} · ${s.method.ref}` }),
    el("div", { class: "footnote", text: COPY["signals.window"].replace("{n}", String(s.method.n))
      .replace("{from}", s.method.window_start.slice(0, 16)).replace("{to}", s.method.window_end.slice(0, 16)) }),
    ...limitLines(s).map((t) => el("div", { class: "footnote", text: t })),
  );
  const open = selfCheckFor(prompts, s);
  return el("article", { class: `tile signal ${cls}`, "data-signal": s.id },
    el("div", { class: "title", text: COPY[`signals.title.${s.id}`] ?? s.id }),
    el("div", { class: "age", text: COPY[`signals.state.${s.state}`] }),
    el("p", { text: headline(s) }),
    ...missingLines(s).map((t) => el("p", { class: "footnote", text: t })),
    ...(s.id === "cabin_vs_earth" ? [...lagLines(s).map((t) => el("p", { class: "footnote", text: t })),
      el("p", { class: "footnote", text: COPY["signals.pair.noBest"] })] : []),
    spark(sparkValues(s)),
    chips(s, now),
    open ? el("p", { class: "footnote", text: COPY["signals.selfCheck"] }) : null,
    how,
  );
}

export function renderSignalsBody(root: HTMLElement, body: SignalsBody | null, prompts: Prompt[], now: number): void {
  if (!body) {
    root.replaceChildren(el("p", { text: COPY["signals.none"] }));
    return;
  }
  const sections = GROUPS.flatMap((g) => {
    const mine = body.signals.filter((s) => groupOf(s.id) === g);
    if (!mine.length) return [];
    return [el("section", {}, el("h2", { text: COPY[`signals.group.${g}`] }),
      el("div", { class: "grid" }, ...mine.map((s) => signalCard(s, prompts, now))))];
  });
  root.replaceChildren(el("p", { text: COPY["signals.intro"] }), ...sections, el("p", { class: "footnote", text: DISCLAIMER }));
}

export function renderSignals(root: HTMLElement): () => void {
  let disposed = false;
  let token = 0;
  const load = async () => {
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const [body, prompts] = await Promise.all([
      getSignals(crew).catch(() => null),
      getPrompts(crew, "open").catch(() => [] as Prompt[]),
    ]);
    if (disposed || mine !== token) return;
    renderSignalsBody(root, body, prompts, Date.now());
  };
  void load();
  const t = setInterval(() => void load(), REFRESH_MS);
  const off = onCrewChange(() => void load());
  return () => {
    disposed = true;
    clearInterval(t);
    off();
  };
}
```

Modify `console/src/screens.ts`:

```diff
--- a/console/src/screens.ts
+++ b/console/src/screens.ts
@@ -1,4 +1,4 @@
-export const SCREENS = ["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "prompts", "body"] as const;
+export const SCREENS = ["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "signals", "prompts", "body"] as const;
 export type Screen = (typeof SCREENS)[number];
 
 /** The screen named in the hash, or `fallback` (the panel, in the console and in the replay build). */
```

Modify `console/src/main.ts`:

```diff
--- a/console/src/main.ts
+++ b/console/src/main.ts
@@ -15,6 +15,7 @@
 import { renderHistory } from "./views/history";
 import { renderLanes } from "./views/lanes";
 import { renderPanel } from "./views/panel";
+import { renderSignals } from "./views/signals";
 import { entryForTile, openGuidance, setLinkState } from "./views/guidance";
 import { refreshBanner, renderNasa, startBanner } from "./views/nasa";
 import { loadBoard, renderStatus } from "./views/status";
@@ -92,6 +93,7 @@
     else if (cur === "exercise") dispose = renderExercise(screen);
     else if (cur === "nasa") dispose = renderNasa(screen);
     else if (cur === "food") dispose = renderFood(screen);
+    else if (cur === "signals") dispose = renderSignals(screen);
     else screen.append(el("p", { text: COPY["screen.pending"] }));
   };
   window.addEventListener("hashchange", render);
```

Modify `console/src/styles.css`:

```diff
--- a/console/src/styles.css
+++ b/console/src/styles.css
@@ -144,3 +144,9 @@
 .food-scan { margin: 0.5rem 0; }
 .food-scan-video { display: block; width: min(100%, 320px); margin-top: 0.5rem; border-radius: 6px; }
 .food-scan-video[hidden] { display: none; }
+
+/* D45 signals */
+.signal p { margin: 6px 0; }
+.spark { width: 100%; height: 30px; margin: 4px 0; }
+.spark svg { width: 100%; height: 100%; display: block; }
+.spark polyline { fill: none; stroke: var(--muted); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
npm --prefix console test -- tests/signals.test.ts tests/smoke.test.ts
```

Expected:

```text
Tests  7 passed (7)
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
npm --prefix console run typecheck && npm --prefix console test
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add console/src/main.ts console/src/screens.ts console/src/styles.css console/src/views/signals.ts console/tests/signals.test.ts console/tests/smoke.test.ts
git commit -m "feat(console): the #/signals screen"
```

### Task 17: Console: the panel's "Signals: N notable" chip

One chip in the panel's top bar, linking to `#/signals`. The recorded-replay panel has no signals source, so its top bar is unchanged.

**Files:**
- Modify: `console/tests/signals.test.ts`
- Modify: `console/src/views/panel.ts`
- Modify: `console/src/views/panel/source.ts`
- Modify: `console/src/views/panel/topbar.ts`
- Modify: `console/src/styles.css`

**Interfaces:**
- Consumes: Task 15's `notableCount`, `getSignals`.
- Produces: `PanelSource.signals?(crew)`; `TopData.signals?: SignalsBody | null` (undefined: no chip; null: request failed, chip says no data).

- [ ] **Step 1: Write the failing test**

Modify `console/tests/signals.test.ts`:

```diff
--- a/console/tests/signals.test.ts
+++ b/console/tests/signals.test.ts
@@ -4,6 +4,7 @@
 import type { Prompt, Signal, SignalsBody } from "../src/contract";
 import { fmt, groupOf, headline, lagLines, missingLines, notableCount, selfCheckFor } from "../src/model/signals";
 import { renderSignalsBody } from "../src/views/signals";
+import { topBar } from "../src/views/panel/topbar";
 
 const NOW = Date.parse("2026-11-20T10:00:00Z");
 
@@ -88,3 +89,18 @@
     expect(root.textContent).toContain("the signals feature is off");
   });
 });
+
+describe("panel top bar signals chip", () => {
+  test("shows the notable count live, and nothing in the replay", () => {
+    const live = topBar({ replay: false, now: () => NOW });
+    live.update({ status: null, sessions: null, weather: null, link: null,
+      signals: { crew: null, at: "x", signals: [sig({ state: "notable" })] } });
+    expect(live.node.textContent).toContain("Signals 1 notable");
+    expect(live.node.querySelector('a[href="#/signals"]')).not.toBeNull();
+    live.dispose();
+    const replay = topBar({ replay: true, now: () => NOW });
+    replay.update({ status: null, sessions: null, weather: null, link: null });
+    expect(replay.node.textContent).not.toContain("Signals");
+    replay.dispose();
+  });
+});
```

- [ ] **Step 2: Run the tests and see them fail**

```bash
npm --prefix console test -- tests/signals.test.ts
```

Expected (first error and summary):

```text
AssertionError: expected 'Cabin sensors No dataLast set none ye…' to contain 'Signals 1 notable'
Tests  1 failed | 5 passed (6)
```

- [ ] **Step 3: Write the implementation**

Modify `console/src/views/panel.ts`:

```diff
--- a/console/src/views/panel.ts
+++ b/console/src/views/panel.ts
@@ -65,8 +65,9 @@
       lanesDue ? laneRows(src, new Date(win[0] * 1000).toISOString(), crew) : Promise.resolve(undefined),
       soft(src.issCabin()), soft(src.issReference()),
     ]);
+    const signals = src.signals ? await soft(src.signals(crew)) : undefined;
     if (disposed || mine !== token) return;
-    top.update({ status, sessions: set.sessions, weather, link: linkState });
+    top.update({ status, sessions: set.sessions, weather, link: linkState, signals });
     lift.update(set);
     places.update(set);
     mass.update({ weighIns, food, training, sessions: set.sessions });
```

Modify `console/src/views/panel/source.ts`:

```diff
--- a/console/src/views/panel/source.ts
+++ b/console/src/views/panel/source.ts
@@ -1,10 +1,10 @@
 import {
   getExerciseDay, getFoodDay, getIssCabin, getIssReference, getLink, getReadings, getReps, getSessions, getSpaceWeather,
-  getStatus,
+  getSignals, getStatus,
 } from "../../api";
 import type {
-  CrewId, ExerciseDay, FoodDay, Ind, IssCabin, IssReference, LinkState, RepsBody, Session, SpaceWeather, StatusBody,
-  StoredReading,
+  CrewId, ExerciseDay, FoodDay, Ind, IssCabin, IssReference, LinkState, RepsBody, Session, SignalsBody, SpaceWeather,
+  StatusBody, StoredReading,
 } from "../../contract";
 
 /**
@@ -30,6 +30,8 @@
   issCabin(): Promise<IssCabin>;
   issReference(): Promise<IssReference>;
   link(): Promise<LinkState>;
+  /** D45 signals. A source without it (the recorded replay) shows no signals chip. */
+  signals?(crew?: CrewId): Promise<SignalsBody>;
 }
 
 /** What a card needs to know about its source: its clock, and whether it is a replay. */
@@ -48,4 +50,5 @@
   issCabin: getIssCabin,
   issReference: getIssReference,
   link: getLink,
+  signals: (crew) => getSignals(crew),
 };
```

Modify `console/src/views/panel/topbar.ts`:

```diff
--- a/console/src/views/panel/topbar.ts
+++ b/console/src/views/panel/topbar.ts
@@ -1,9 +1,10 @@
 import { COPY } from "../../copy";
-import type { LinkState, Session, SpaceWeather, StatusBody } from "../../contract";
+import type { LinkState, Session, SignalsBody, SpaceWeather, StatusBody } from "../../contract";
 import { el } from "../../dom";
 import { formatAge } from "../../format";
 import { formatLightTime } from "../../model/guidance";
 import { weatherBanner } from "../../model/nasa";
+import { notableCount } from "../../model/signals";
 import { liveSource, type PanelClock } from "./source";
 
 export interface TopData {
@@ -11,6 +12,8 @@
   sessions: Session[] | null;
   weather: SpaceWeather | null;
   link: LinkState | null;
+  /** D45: undefined when the source has no signals (replay); null when the request failed. */
+  signals?: SignalsBody | null;
 }
 
 function chip(dot: string, label: string, value: string): HTMLElement {
@@ -49,6 +52,13 @@
       chip(d.link?.state === "contact" ? "ok" : d.link?.state === "blackout" ? "act" : "",
         COPY["panel.chipLink"], d.link ? formatLightTime(d.link.light_time_s, 1) : missing),
     );
+    if (d.signals !== undefined) {
+      const n = notableCount(d.signals);
+      const link = el("a", { href: "#/signals", class: "pchip-link" },
+        chip(n > 0 ? "watch" : "", COPY["panel.chipSignals"],
+          d.signals ? COPY["panel.signalsNotable"].replace("{n}", String(n)) : missing));
+      chips.append(link);
+    }
   };
   return { node, update, dispose: () => clearInterval(t) };
 }
```

Modify `console/src/styles.css`:

```diff
--- a/console/src/styles.css
+++ b/console/src/styles.css
@@ -150,3 +150,4 @@
 .spark { width: 100%; height: 30px; margin: 4px 0; }
 .spark svg { width: 100%; height: 100%; display: block; }
 .spark polyline { fill: none; stroke: var(--muted); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
+.pchip-link { color: inherit; text-decoration: none; display: contents; }
```

- [ ] **Step 4: Run the tests and see them pass**

```bash
npm --prefix console test -- tests/signals.test.ts
```

Expected:

```text
Tests  6 passed (6)
```

- [ ] **Step 5: Check the whole suite and lint**

```bash
npm --prefix console run typecheck && npm --prefix console test
python -m pytest -q -m 'not broker'
```

Expected: no new failures. On a fresh clone the only known failure is `test_firmware_tilt.py::test_readme_safety_and_no_company_name` when a local `secrets.h` exists (test-gap analysis item 7); it is not caused by this task.

- [ ] **Step 6: Commit**

```bash
git add console/src/styles.css console/src/views/panel.ts console/src/views/panel/source.ts console/src/views/panel/topbar.ts console/tests/signals.test.ts
git commit -m "feat(console): Signals: N notable chip on the panel"
```

### Task 18: Whole-module check and the replay demo

- [ ] **Step 1: Run every suite** on the slice-6 branch:

```bash
ruff check hub nodes
python -m pytest -q -m 'not broker'
npm --prefix console run typecheck && npm --prefix console test && npm --prefix console run build
```

Expected: no new failures against `main`.

- [ ] **Step 2: Run the replay demo** on a scratch hub (never the live hub's DB) and look at `#/signals` in a browser:

```bash
HUB_DB=var/scratch-signals.db HUB_HTTP_PORT=8010 python -m hub &
python -m hub.sim --file data/replay/signals-synthetic-28d.jsonl --backdate --http http://127.0.0.1:8010
```

Check by eye, for crew A: resting HR "Above your own usual range" and notable; cabin humidity "At this rate, reaches
75.0 % in about 3–4 h, if nothing changes" (steady, under the 3-hour notable line); water logged trend up; the lift
cards greyed with "Needs 6 reps…"/"Needs 10 sets…"; every chip "Replay (recorded)". For crew B: every card greyed (the
replay never writes crew B). The trigger opens no prompt for the replay (decision 4): `GET /api/prompts` stays empty
of `signal_*` kinds. On real data, a ★ signal changing from steady to notable opens one prompt within 5 minutes.

- [ ] **Step 3: Check the wording once more** against the Global Constraints: no "prediction" except "not a prediction",
no kcal next to joules, every number with its interval.

- [ ] **Open the slice's draft PR** (never merge it; the team owner merges):

```bash
git push -u origin HEAD
gh pr create --draft --base main --title "feat(console): D45 signals screen and panel chip" --body "Implements D45 slice 6 (docs/decisions/2026-11-15-signals-module-design.md). Plan: docs/plans/2026-11-15-signals-module-plan.md, tasks 15–18."
```

---

## Spec coverage

| Spec section | Where |
|---|---|
| §4.1 package, feature gate, routes | Tasks 2, 3 |
| §4.2 ISS Live stored; Earth weather importer; contract additions | Tasks 6, 7, 8, 9 |
| §4.3 nothing else changes | Task 6 (quiet feeds, off `/api/status`); Task 3 test (feature off = 404) |
| §5 signal object and honesty rules 1–7 | Task 2 (object, `not_enough_data`, `missing`), Task 15 (wording, `rulePrediction`), Tasks 2/11/12 (replay never pools), Task 12 (no energy arithmetic) |
| §6.1 Mann-Kendall + Sen, blocking, minimums | Tasks 1, 2 |
| §6.2 own baseline | Tasks 1, 2, 11 |
| §6.3 time-to-limit (incl. ppCO2 1-hour mean) | Tasks 1, 2 |
| §6.4 lagged pairs, lags 0–3 h, no best lag | Tasks 1, 12 |
| §6.5 input definitions | Tasks 2, 10, 11, 12 |
| §7 the 19-signal catalogue | Tasks 2 (9), 6 (1), 10 (2), 11 (3), 12 (4) |
| §8 trigger, prompt kinds, `signal_events`, link payload | Tasks 13, 14 |
| §9.1 console screen, panel chip, lint | Tasks 15, 16, 17 (popup: decision 6) |
| §9.2 replay with planted effects | Tasks 4, 8, 12 (lift on replay: decision 7) |
| §10 testing | every task's tests; Task 18 |
| §11 build order (6 slices) | Slices 1–6 |
| §12 out of scope | not built: link digest, public signals, camera features, dose signals, kcal links, ML, assessment status, tilt lag correction |
| §13 open points | decided 2026-11-15: Task 5 (record), Task 9 (INMET adapter) |

## Execution notes

- Tasks run in order inside a slice. Slices 1 → 2 → 3/4 → 5 → 6: slice 4 needs slice 3's contract additions (Task 6) for
  `cabin_vs_earth`; slice 5 needs slice 2; slice 6 needs the API shape of slices 2–5.
- Each task's tests fail first for the reason shown (a missing module or a changed assertion), then pass. If a test fails
  for another reason, stop and check before changing the test.
- Always run pytest with `-m 'not broker'`: the broker tests talk to a real Mosquitto, never the bench broker.
- The replay file is generated; regenerate it with the command in Task 4, never edit it by hand. Its test compares the
  committed bytes with the generator.
