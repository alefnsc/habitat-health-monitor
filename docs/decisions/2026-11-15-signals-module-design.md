# Cross-reference and predictive signals module — design (D45)

Status: design sections 1–6 approved by the team owner, 2026-11-15 (UTC−03:00). This is **post-event** work. It
does not change the build submitted to NASA Space Apps on 2026-11-15, and nothing here is implemented yet.

The team owner's request: "cross-reference and predictive signals module on habitat based on food, health, ring
metrics, computer vision and atm data + sensors humidity temp inclination".

## 1. Goal

The hub gains **signals**: labelled trends, own-baseline deviations, short cabin time-to-limit estimates and
side-by-side cross-references. They are built from data the hub already stores, plus two new stored feeds. The
**crew on board** reads them first, on the console, next to the data they come from. A notable signal may open a
**self-check** (the existing prompt flow). It never raises an alert.

Every signal shows its inputs, method, interval and limits. A signal that cannot be computed honestly says
`not enough data` and names what is missing.

## 2. Decisions taken in the brainstorm

| # | Question | Decision |
|---|---|---|
| Q1 | First reader | The crew on board (console). Not the ground, not the public page. |
| Q2 | What "atm data" means | All four: cabin atmosphere (bench DHT11, plus CO2/pressure when a source exists), ISS Live atmosphere, DONKI space weather, and outdoor Earth weather. |
| Q3 | Signal kinds | All four: trends with uncertainty, own-baseline deviation, cabin time-to-limit, lagged cross-reference. |
| Q4 | What a signal may trigger | It may open a self-check prompt. It never raises an alert, sounds the buzzer or sends a link packet. |
| Q5 | Data | Synthetic and real: a labelled 28-day synthetic replay for tests and demo, and the same signals on real data once there is enough of it. |
| Q6 | Computer vision and inclination | The stored camera reps and the tilt witness (D39). No new camera features. |
| Approach | Architecture | **A: computed on read** in the hub. The alternatives were a materialized signals table (B) and console-side models (C). |

**Why A.** Ring data is a delayed cloud sync. It lands hours late with its true `measured_at`, so a stored signal
computed before the sync would be stale or wrong afterwards. B would need an invalidation step to handle that. C
cannot open a self-check, would keep the statistics in TypeScript, and would still need hub work to store the ISS and
Earth feeds. Computing on read also keeps "missing stays missing" simple: the engine sees exactly what is stored.

## 3. Facts from the code that shape the design (main `239924d`)

- Readings are assessable only when `q == ["ok"]` (`hub/contract.py:is_assessable`). Body and intake indicators are
  crew-scoped (`hub/assess.py:CREW_SCOPED`). Cabin indicators are not.
- **Ring (`nodes/ring/mapper.py`).** The importer covers `crew-b` only, node `ring-1`, src `hobby`. It maps:
  - `hr` from rest and sleep samples only (the ring's 5-minute series; awake, workout, live and session samples are
    dropped), so **there is no ring HR during a camera set**;
  - `spo2` as the nightly average, timed at the night's end;
  - `sleep_h` as the main sleep only, timed at `bedtime_end`.

  There is no sleep start, so the night window is `(sleep_end − sleep_h, sleep_end]`.
- **Bench cabin.** `cabin-1` is a DHT11 giving `cabin_temp` and `cabin_rh` every 5 s. There is no CO2 or pressure
  sensor on the bench. `cabin_ppco2` exists only from replay or a later sensor.
- **Camera reps (`hub/contract.py:Rep`).** Each rep has `work_j`, `rom_m`, `g`, `mass_kg`, `t_con_ms`, `t_ecc_ms`,
  `t_turn_ms` and `exercise`, plus the session's crew. The tilt witness (`hub/tilt.py:tilt_for_rep`) is computed on
  read and gives `seen`, `turn_inside` and `offset_ms` (about 200 ms of debounce lag, not yet corrected).
- **Food (`hub/food/day.py`).** Intake readings are summed over a rolling 24 h. A crew-less meal is never counted
  for a crew.
- **ISS Live (`hub/nasa/isslive.py`).** Cabin pressure, cabin temperature and two ppCO2 items are held **in memory
  only**.
- **DONKI.** The space-weather level is stored as the `space_weather` reading (0, 1 or 2) and judged by
  `radiation_spe`.
- **An existing trend.** `console/src/model/panel/trend.ts` fits a least-squares line to weigh-ins and labels it
  "not a prediction". The honesty lint is `console/tests/honesty.ts`.
- **Prompts (`hub/prompts.py`).** Prompts already exist with kinds `morning`, `post_exercise` and `cabin_trigger`.
  Answers go to the outbox as `prompt_answer`. The link consent filter (`linksim/consent.py`) lets an answer reach the
  public page only for a crew in `PUBLIC_CREWS`.

## 4. Architecture (section 1, approved)

### 4.1 Package `hub/signals/`

The package is feature-gated as `signals` in `hub/features.py:_TABLE`, the same way as `food`. A failed import lands
in `Features.skipped` and the hub still starts.

| Module | Purpose | Depends on |
|---|---|---|
| `methods.py` | Pure statistics: Mann-Kendall with tie correction, the Sen slope and its confidence interval, a median/MAD baseline, a time-to-limit interval, lagged pairing, Spearman ρ with a Fisher-z interval. Standard library only (`math`, `statistics`). | nothing |
| `inputs.py` | Store rows to blocked series: 10-minute and 5-minute cabin medians, nightly values from the night window, daily food totals, per-set rollups. It reads only assessable rows and **never fills a gap**. | `Store`, `hub/tilt.py`, `hub/exercise.py:latest_reps` |
| `catalogue.py` | The signals as data: id, kind, inputs, window, minimum n, coverage, method, wording key, whether it can trigger, and the `rule_id` of any band it names. | the loaded `Rule` list |
| `engine.py` | `evaluate(store, rules, crew, at) -> list[Signal]` and `evaluate_one(id, …)`. | the three above |
| `trigger.py` | The periodic self-check evaluator (section 8). | `engine.py`, `PromptManager` |
| `routes.py` | `GET /api/signals?crew=&at=` (every signal) and `GET /api/signals/{id}?crew=&at=` (one signal with its blocked series). | `engine.py` |

`at` defaults to the hub clock. A past `at` makes tests and replays reproducible.

### 4.2 Two new stored feeds (prerequisites)

Both arrive as **contract-v1 readings** through the normal ingest door, so the assessor, store and charts treat them
like any other reading.

1. **ISS Live atmosphere.** The existing ISS client also writes three readings through `Ingestor.ingest_internal`:
   - `iss_cabin_p`, `iss_cabin_temp` and `iss_ppco2`, the last from `USLAB000055`; `NODE3000003` is kept as a
     second `iss_ppco2` reading told apart by `seq`;
   - every row uses node `nasa`, src `nasa` and a new dev `ISSLIVE`;
   - at most one row per item per minute, and only when the item is fresh.

   Units are converted to the hub's units in slice 3, after checking what each item publishes.
2. **Earth weather (outdoor).** A **separate process**, `nodes/weather`, follows the ring importer's pattern, so the
   habitat core stays offline.
   - It posts `earth_temp` (C), `earth_rh` (%) and `earth_p` (hPa) with a new node `earth-1`, a new src `ref` and a
     generic new dev `WEATHER`.
   - The console labels it "Earth reference, outdoor".
   - The location is a coarse grid cell held in `.env`. It is never committed, published or shown.
   - The provider is an open, keyless API, named only in `DATA_SOURCES.md` (R5).
   - Failures are logged and retried at the next run. Missing hours stay missing.

The contract gains the six indicators, node `earth-1`, src `ref` and devs `ISSLIVE` and `WEATHER`. None of the new
indicators is crew-scoped. None is in `CABIN_INDS`, `NASA_INDS` or `PERSONAL_INDS`, so the consent filter keeps them
off the public page unchanged.

### 4.3 What does not change

- The assessor, `data/thresholds.json`, the existing endpoints, the panel layout and the public ground page.
- Signals never write a reading, an assessment or an alert.
- Signals never cross the link (the self-check answer, see 8.3, is the crew's own answer and travels as answers do
  today).

## 5. The signal object and the honesty contract (section 2, approved)

```text
Signal {
  id, kind: "trend" | "baseline" | "time_to_limit" | "lagged_pair",
  crew,                                   # None for cabin, ISS and Earth signals
  state: "notable" | "steady" | "not_enough_data",
  headline_key,                           # wording lives in console copy, never built in the hub
  value: { estimate, low, high, unit, per } | null,
  method: { name, ref, alpha, n, min_n, window_start, window_end, coverage },
  inputs: [ { ind, src, dev, node, n, first_at, last_at, oldest_age_s } ],
  missing: [ "needs 7 nights; have 4", ... ],   # filled when state is not_enough_data
  limits: [ "consumer ring estimate", "5-minute samples, rest and sleep only", ... ],
  reference: { rule_id, source_kind } | null,   # only when a NASA or clinical band is named
  replay: bool
}
```

The rules below are enforced by tests or by the lint.

1. **No bare number.** Every estimate has a `low`–`high` interval. The interval is the slope interval for a trend,
   the own usual range for a baseline, the hours interval for a time-to-limit, and ρ's interval for a lagged pair.
   When an interval cannot be computed, the state is `not_enough_data`.
2. **Missing data stays missing.**
   - Below `min_n`, or below the coverage rule, the state is `not_enough_data` and `missing` says what is needed.
   - There is no interpolation, no imputation and no carrying a value forward.
   - A day with no meal logged has no intake value, not zero.
3. **Wording is fixed by kind.** The copy lives in `console/src/copy.ts`.
   - Allowed words: "trend", "own usual range", "at this rate", "if nothing changes", "side by side".
   - The lint gains `rulePrediction`, which bans "predict", "prediction", "forecast", "risk" and "will", with the
     existing "not a prediction" phrase allowed. It runs over the signal strings only (the `signals.*` copy keys and
     the hub's `limits` strings), so existing console copy is not affected.
   - The existing rules still apply: diagnosis, "measured", "validated" and "accurate" for estimates, calories
     wording, "balance", "deficit", brand names.
   - A time-to-limit signal always reads: "At this rate, reaches {limit} in {low}–{high} h, if nothing changes."
4. **Sources are labelled.**
   - `inputs[].src` and `dev` are carried through to the console's existing source chips: "Ring (delayed cloud sync)
     · 7 h ago", "Camera estimate", "Replay (recorded)", and the new "Earth reference, outdoor" and "ISS, NASA public
     telemetry".
   - A signal with any replay input has `replay: true` and is shown as replay. Replay and real rows are never pooled
     in one signal: the engine evaluates the replay crews and the real crews separately.
5. **No energy arithmetic.** Camera joules and food kcal are never added, subtracted or converted. No catalogue entry
   takes both a rep input and an intake input in one value. The lagged pairs only set them side by side.
6. **Bands are context only.** A signal may name a band ("heading for the 75 % NASA limit") through `reference`. It
   never sets an assessment status. A `clinical_ref` band keeps its "Not NASA-published" note next to it.
7. **Consent and data rules.**
   - Body and intake signals are crew-scoped exactly like `CREW_SCOPED`.
   - Signals appear only on the console. There is no public path.
   - R8: no data of the minor team member is imported. The synthetic crews are invented.
   - R5: no company or vendor name appears in any signal text or `limits` string.

## 6. Methods and minimum data (section 3, approved)

All methods are standard-library Python. Each method's `method.ref` names its source, and each is tested against a
published worked example (section 10).

### 6.1 Trend: Mann-Kendall test with the Sen slope

- The test uses Mann's S statistic with the tie-corrected variance and the normal approximation, two-sided at
  α = 0.05. References: Mann (1945); Kendall (1975); Gilbert (1987), *Statistical Methods for Environmental
  Pollution Monitoring*, ch. 16.
- The slope is Sen's (1968): the median of all pairwise slopes. Its confidence interval comes from the rank method in
  Gilbert (1987) §16.5.
- **Points are blocked first, because raw samples are serially correlated:**
  - cabin, ISS and Earth series become 10-minute medians over 6 h (36 blocks);
  - body series become one value per night or per day over 14 days;
  - lift series become one value per set.
- **Minimum:** n ≥ 10 blocks, and the blocks present cover at least 75 % of the window.
- **Notable:** p < 0.05 *and* the slope's interval excludes 0.
- **Limit shown on every trend:** "Assumes independent points. Blocking reduces serial correlation but does not
  remove it."

### 6.2 Own-baseline deviation

- The baseline is the median and MAD of the previous 14 days, **excluding today**. It needs at least 7 prior values.
- The own usual range is median ± 2 × 1.4826 × MAD. A MAD of 0 (all prior values equal) gives `not_enough_data`
  with "no spread yet".
- The value shown is today's, next to the range.
- **Notable:** outside the range on two days in a row. A single day is shown and is never notable.
  `spo2_baseline` counts only values below the range.

### 6.3 Time-to-limit (cabin only)

- **Fit:** the Sen slope and its interval over the last 2 h of 5-minute medians (24 blocks, at least 18 present).
  "Current" is the median of the last three blocks.
- **Limit:** read from the loaded rules by `rule_id`, never hard-coded: `cabin_health_box_temp` (18–27 °C),
  `cabin_health_box_rh` (25–75 %) and `co2_1h` (3 mmHg). The side the slope heads toward is used.
- **Interval:** the time to the limit at the slope's two bounds, in hours.
- **Shown only when** the slope interval excludes 0, points toward the limit, and the far end of the hours interval
  is at most 12 h. Otherwise the state is `steady`, with the trend line still available.
- **Notable:** the near end of the hours interval is under 3 h.
- **Limit text:** "A straight-line extension of the last 2 hours. Opening a hatch, a person entering or the HVAC
  cycling changes it."
- `co2_1h` judges a 1-hour mean, so `cabin_ppco2_ttl` fits the trailing 1-hour mean series (as
  `hub/buckets.py:trailing_means` builds it), not the raw blocks.

### 6.4 Lagged cross-reference (descriptive)

- Pairs a value from day d with one from night d → d+1 (or day d+1) for the same crew. `cabin_vs_earth` uses hourly
  medians instead and shows one table per lag (0, 1, 2 and 3 h). No lag is picked as the "best" one, because picking
  the best of four would overstate the association.
- **Under 20 pairs:** only the side-by-side table, plus "n = {n}, too few pairs to say anything".
- **20 pairs or more:** adds Spearman ρ with a Fisher-z interval (standard error 1.03 / √(n − 3), Fieller, Hartley
  and Pearson 1957) and "Association in your own data, not cause." Hourly pairs also get "Hours next to each other
  are not independent; the interval is too narrow."
- **Never notable**, so a lagged pair never opens a self-check.

### 6.5 Input definitions

| Input | Definition |
|---|---|
| Night window | `(sleep_end − sleep_h, sleep_end]` from the crew's `sleep_h` reading. A night with no `sleep_h` has no window. |
| Nightly resting HR | The median of the 5-minute HR blocks (ring `hr`, crew-scoped) inside the night window. Needs at least 50 % of the window's blocks present. |
| Nightly SpO2, nightly sleep | The ring's `spo2` and `sleep_h` reading for that night. |
| Daily intake | The 24 h total for a local day, built the same way as `hub/food/day.py`. A day with no meal has no value. |
| Body mass | Logged `body_mass` readings: at most one per day (the last), over 30 days. |
| Per-set rollup (one per session) | `latest_reps` camera reps of the session's crew. Fields: rep count, median of `work_j / g` (mass × ROM, so sets at different g compare), medians of `t_con_ms` and `t_ecc_ms`, the ratio of eccentric to concentric time, the coefficient of variation of rep duration, the share of reps with `tilt.seen`, and the median absolute `tilt.offset_ms`. |
| Daily training work | The sum of `work_j / g` over the crew's camera sets that day, in J/(m/s²), shown as "camera estimate". It is never converted to food energy. |
| Last meal time | The local time of the crew's last logged meal of the day. |
| Space-weather day | The highest `space_weather` level stored that local day. |

## 7. The v1 catalogue (section 4, approved)

★ marks the signals that can open a self-check (section 8).

| id | kind | inputs | The crew sees |
|---|---|---|---|
| `cabin_temp_6h` | trend | `cabin_temp` (bench) | Cabin temperature trend over 6 h, in °C per hour with its interval |
| `cabin_rh_6h` | trend | `cabin_rh` (bench) | Cabin RH trend over 6 h |
| `cabin_temp_ttl` ★ | time_to_limit | `cabin_temp`, rule `cabin_health_box_temp` | "At this rate, reaches 27 °C in X–Y h, if nothing changes" |
| `cabin_rh_ttl` ★ | time_to_limit | `cabin_rh`, rule `cabin_health_box_rh` | The same, for 25 % or 75 % |
| `cabin_ppco2_ttl` ★ | time_to_limit | `cabin_ppco2` (1-hour mean), rule `co2_1h` | Only when a CO2 source exists (replay today) |
| `iss_ppco2_6h` | trend | `iss_ppco2` | ISS ppCO2 trend, "ISS, NASA public telemetry" |
| `cabin_vs_earth` | lagged_pair | `cabin_temp` vs `earth_temp`, hourly, lag 0–3 h | "The bench room side by side with outdoor temperature" |
| `rest_hr_baseline` ★ | baseline | nightly resting HR | Last night's resting HR next to your own usual range |
| `rest_hr_14n` | trend | nightly resting HR | Resting HR trend over 14 nights |
| `sleep_baseline` ★ | baseline | nightly `sleep_h` | Last night's sleep next to your own usual range |
| `spo2_baseline` ★ | baseline | nightly `spo2` | Only below the range counts as notable |
| `body_mass_30d` | trend | `body_mass` | Sen slope in kg per week, with its interval. The panel's arithmetic line stays as it is. |
| `water_14d` | trend | daily `intake_water_ml` | Water logged, trend over 14 days |
| `lift_work_sets` | trend | per-set median `work_j / g`, one exercise at a time | Work per rep across your sets |
| `lift_within_set` | trend | the latest set's reps (6 or more), `work_j / g` | "Work per rep fell (or held) across the set". No physiology words. |
| `lift_tilt_agreement` | baseline | per-set tilt-witness share and median offset | The latest set against your usual camera–tilt agreement: a check on the rig and camera timing, not on the crew |
| `training_vs_rest_hr` | lagged_pair | daily training work (day d) vs nightly resting HR (night d → d+1) | Side by side, with n |
| `last_meal_vs_sleep` | lagged_pair | last meal time (day d) vs `sleep_h` (night d → d+1) | Side by side, with n |
| `space_weather_vs_sleep` | lagged_pair | space-weather day (d) vs `sleep_h` (night d → d+1) | Always carries "The bench crew is on Earth, shielded by the atmosphere. This pairing shows the method, not an effect." |

**Left out of v1, on purpose:**
- Radiation-dose signals. The dose is a linear estimate, so a trend on it would restate its own formula.
- Any signal that mixes joules with kcal.
- New camera features.
- Signals in a link digest.

## 8. The self-check trigger (section 5, approved)

### 8.1 Evaluation

`trigger.py` runs in `FeatureRuntime` every 5 minutes, started and stopped like the NASA poller. It evaluates only
the ★ signals:
- the three cabin time-to-limit signals with crew None;
- the three body baselines for each crew in `settings.crews` that has data.

### 8.2 When a prompt opens

- A prompt opens only on a transition from `steady` to `notable`. A change from `not_enough_data` to `notable` does
  not count until one `steady` evaluation has been seen, so data appearing for the first time does not flood the
  crew.
- There are two new prompt kinds in `PROMPT_ASKS`:
  - `signal_cabin` asks for `("symptom",)`;
  - `signal_body` asks for `("symptom", "mood")`.
- `PromptManager.create(...)` gains one optional `trigger=` dict. It holds the signal snapshot (id, state, value and
  interval, inputs, limits), so the console can show why it asked. Signal prompts have no `trigger_reading_id`.
- A new table records every transition, including those that open no prompt:
  `signal_events(id, signal_id, crew, state, at, prompt_id, snapshot)`. It handles dedupe and audit:
  - no new prompt while one is open for the same signal and crew;
  - a cooldown after each prompt: 2 h for cabin signals, 24 h for body signals.
- The trigger never writes an alert, an outbox `alert` row or a command, and never sounds the buzzer.

### 8.3 What crosses the link

- The **answer** to a signal prompt is an ordinary `prompt_answer`. It crosses the simulated link like any answer,
  and the consent filter is unchanged.
- Its payload has `prompt_kind` set to `signal_cabin` or `signal_body`, `rule_id` set to null, and **no signal
  values**. The snapshot stays on board in `signal_events`.

### 8.4 Failure handling

- An exception in one signal is logged and skips only that signal. An exception in the trigger loop is logged and the
  loop goes on at the next tick. Neither stops the hub, following the `_guard` pattern in `hub/features.py`.

## 9. Console and replay data (section 6, approved)

### 9.1 Console

- **A new screen, `#/signals`,** has one card per signal, grouped Cabin · Body · Food · Lift · Cross-reference. Each
  card shows:
  - the headline from `copy.ts`;
  - the estimate with its interval;
  - a sparkline of the blocked series;
  - the source chips, with their age;
  - n and the window;
  - a "How this is worked out" toggle with the method, reference, α and limits.

  Cards in `not_enough_data` are drawn greyed with their `missing` lines, never hidden. Lagged pairs show their
  side-by-side table.
- **The panel is unchanged in v1** except for one top-bar chip, "Signals: N notable", linking to `#/signals`. That
  keeps the submitted panel layout intact.
- The self-check popup shows the signal snapshot from the prompt's `trigger`.
- `console/tests/honesty.ts` gains `rulePrediction`. The copy test covers every signal string.

### 9.2 Replay data

`data/replay/signals-synthetic-28d.jsonl` holds 28 invented days for the synthetic crews `crew-a` and `crew-c`, all
`src replay` and `node sim-1`, **never** `crew-b`. That keeps it apart from the team owner's real ring data, and R8
is safe. It replays through the existing `hub.sim` path and carries a `note` header saying it is synthetic.

It plants known effects so that tests can check the signals:
- a resting-HR rise over the last 3 nights for `crew-a`;
- a cabin RH ramp that reaches 75 % in about 3–4 h;
- one flat series, which must stay `steady`;
- one series with gaps, which must stay `not_enough_data`;
- camera sets with a falling work per rep in the last set;
- a space-weather day at level 1.

## 10. Testing

- **`methods.py`:**
  - Mann-Kendall and Sen checked against Gilbert's (1987) ch. 16 worked examples;
  - the MAD range checked against a hand-worked case;
  - the time-to-limit interval checked against a hand-worked case;
  - property tests: all ties give no trend; n below `min_n` gives `not_enough_data`; a gap is never filled; a MAD of
    0 gives `not_enough_data`.
- **Engine:** one test per catalogue entry on the replay. Each signal finds its planted effect, stays steady on the
  flat series and reports `missing` on the gapped one. A fixed `at` keeps the tests reproducible.
- **Inputs:**
  - the night window comes from `sleep_h`;
  - crew-less meals never count for a crew;
  - replay and real rows never pool;
  - a late ring sync changes the signal on the next read.
- **Trigger** (fake clock):
  - steady → notable opens exactly one prompt;
  - not_enough_data → notable opens none;
  - cooldowns and the open-prompt dedupe hold;
  - no alert or outbox `alert` row is written.
- **Consent:** a signal prompt's answer payload carries no signal values, and the filter's decisions are unchanged.
- **Feature gate:** a broken `hub.signals` import leaves the hub starting, with the reason in `Features.skipped`.
- **New feeds:**
  - ISS rows are rate-limited and stale items are skipped;
  - the weather importer never posts a missing hour;
  - the location never appears in a committed file (a scan test, like the company-name scan).
- **Console:** the copy lint, the card render with `not_enough_data`, and the chip count.

## 11. Build order

Each slice is its own PR, after the event, from `main`.

1. `hub/signals/methods.py` with its tests. No wiring.
2. `inputs.py`, `engine.py`, `catalogue.py` and `routes.py` for the cabin and body signals, the feature gate, and the
   replay file.
3. The ISS Live storage and the `nodes/weather` importer, with the contract additions (section 4.2).
4. The food, lift and cross-reference signals.
5. `trigger.py`, the two prompt kinds, `PromptManager.create(trigger=)` and `signal_events`.
6. The console: the `#/signals` screen, the top-bar chip, `rulePrediction`, and the self-check popup snapshot.

## 12. Out of scope (v1)

- A signals digest over the link, and any public signal.
- New camera features (smoothness, ROM consistency).
- Signals on radiation dose.
- Any joule-to-kcal conversion or comparison.
- Machine-learning models.
- Signals that set an assessment status.
- Correcting the tilt witness's 200 ms debounce lag. That is its own follow-up (gap analysis, "after the event"),
  and `lift_tilt_agreement` uses its own baseline, so the constant offset cancels out.

## 13. Open points for the team owner's review

- The unit of each ISS Live item, which decides the conversion in slice 3.
- The Earth-weather provider, to be recorded in `DATA_SOURCES.md`.
