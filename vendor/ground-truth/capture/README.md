# @ground-truth/capture

Dependency-free TypeScript, pure functions, no I/O, no clock, no `Math.random`. It
turns a stream of noisy wrist positions from a phone camera into per-repetition work,
peak force and range of motion, or **refuses the session with a stated reason**. The
only dependency is [`@ground-truth/physics`](../physics/README.md), which does the
arithmetic once the positions are clean.

**Nothing in this package has been checked against real video.** Every number in this
file comes from synthetic sessions (a seeded noise generator, ideal minimum-jerk
motion) or is labelled as an estimate. See "What only real video can settle" before
presenting any output as a measurement.

```sh
npm test                                        # from the repo root
npm run typecheck -w @ground-truth/capture
```

```ts
import { analyzeSession, metersPerUnitFromKnownLength, type PoseFrame } from "@ground-truth/capture";

// frames: PoseFrame[] = { tS, wristY, visibility }[]  (see "Adapter contract")
// Calibration: an object of known length (here a 0.30 m ruler) held vertically in the lifting hand,
// its two ends read in one frame. See "Scale" for why this is preferred to the stature method.
const metersPerUnit = metersPerUnitFromKnownLength(0.3, rulerTopY, rulerBottomY);
const r = analyzeSession(frames, { massKg: 20, gEnvMs2: 9.81, metersPerUnit });

if (r.ok) {
  // { startS, durationS, liftDurationS, filterLimited, rangeOfMotionM, pathLengthM, trimmedRangeFraction,
  //   positiveWorkJ, negativeWorkJ, peakForceN, impulseNs }[]
  r.reps;
  r.totalPositiveWorkJ; r.maxPeakForceN;
  r.provenance; // { loadSource: "CAMERA", confidence: "MEDIUM" | "LOW" }  (grades capture conditions, not accuracy)
} else {
  r.reasons; // e.g. ["LOW_FRAME_RATE", "GAP_TOO_LONG"]. No measurement is returned.
}
```

A refusal is a return value, never an exception. It carries the reasons and the
quality diagnostics (frame rate, lost-frame fraction, longest gap, duration, dropped
frames) and no work, force, range of motion or provenance. **No frame content can make
`analyzeSession` throw**: NaN, infinities, duplicate or out-of-order timestamps and
timestamps in the wrong unit are refused or dropped. Invalid *options* (a negative mass,
a cutoff that is not a positive number, a threshold outside its range) are programmer
errors and throw a `RangeError` naming the argument. A cutoff the stream's frame rate
cannot carry (at or above half of it: 12 Hz is fine at 30 fps and impossible at 23.976)
depends on the frames, so it is a refusal, `LOW_FRAME_RATE`.

## Capture protocol

The package separates a repetition from what surrounds it by **pauses**, and by nothing
else. It cannot tell a pick-up from a lift unless the weight stops in between. So:

1. **Hold the weight still for about a second before the first rep**, after picking it
   up, at the height the reps start from.
2. **Pause for about a second after the last rep, before setting the weight down.**
3. **Stand side-on to the camera**, with the whole movement in the frame.
4. **Start and stop the recording while still.**
5. Rests between reps are optional, and any length. A hesitation inside a lift is fine.

A pause counts when it lasts 0.3 s with the wrist still (under about 2 cm/s); a second
gives margin. What happens otherwise, **measured on synthetic signals** (0.5 m curls of
1 s, a 0.6 m pick-up and set-down, 60 Hz):

| Departure from the protocol | What the affected rep reads | Does anything signal it? |
|---|---|---|
| Set-down straight after the last lowering, no pause | Negative work **+120 %** (lowering, then at once a 0.6 m set-down) to **+178 %** (one movement from the top to the floor). Positive work and range of motion are right (−0.5 %). | `trimmedRangeFraction` 0.45 |
| Pick-up straight into the first curl, no pause | Range of motion and positive work **+120 %** (1.10 m for a 0.5 m curl), start 1.1 s early. Negative work is right. | No: `trimmedRangeFraction` reads 1.00 |
| Pick-up and first curl as one movement from the floor | Range of motion and positive work +120 %: the whole 1.10 m is one lift. | No |
| Recording starts mid-lift, or stops mid-lowering | The visible part is counted as a rep; work, range and duration are partial. A lift whose lowering has not yet come down 0.10 m when the recording stops is not a rep: it is left out, and if it was the only one the recording is refused `NO_REPS`. | No, unless it is refused |
| Movement not side-on | Reads as less range of motion. | No |

## Adapter contract

The adapter that turns a pose model's output into `PoseFrame`s (it ships with the demo,
not here) must produce:

- **`tS` in seconds**, strictly increasing, and the **capture time of the frame**, not
  the time a callback ran. Callback time carries scheduling jitter that the pipeline
  cannot tell from motion. Milliseconds are refused (the stream reads as 0.06 Hz), not
  converted.
- **`visibility` 0 when there is no detection.** Do not repeat the last position with a
  high visibility. A non-finite visibility, or a non-finite `wristY`, is treated as a
  lost landmark.
- **`wristY` normalised (0–1) with y pointing down**, as pose models report it. This
  package converts to metres, y up, in exactly one place (`toMetersUp`).
- One entry per delivered frame. A frame processed twice (same timestamp) or delivered
  out of order is *dropped* and counted in `QualityReport.droppedFrames`; more than 10 %
  of the stream dropped this way is refused with `LANDMARK_LOST`.

## The pipeline, in order

| Step | Function | What it does |
|---|---|---|
| 1 | `assessQuality` | Drops frames not in time order, then frame rate, lost frames, gaps, duration. Any reason refuses the session. |
| 2 | `resampleUniform` | Drops low-visibility frames, then linear interpolation onto a uniform grid at the median frame rate. Nothing is extrapolated. |
| 3 | `toMetersUp` | The one place where image coordinates (y down) become metres (y up): `yM = −wristY · metersPerUnit`, first sample 0. |
| 4 | `lowPassZeroPhase` | 2nd-order Butterworth, forward then backward, 4 Hz by default. A recording not longer than the filter's padding is refused `TOO_SHORT`. |
| 5 | `segmentReps` | Displacement hysteresis on position extrema. A recording in which it finds no complete repetition is refused `NO_REPS`. |
| 6 | rep window | Each rep is trimmed to its movement, between the pause before the top and the pause after it whose rest levels agree: the lift starts where the position leaves the first pause's rest level, the lowering ends where it reaches the second's. |
| 7 | `trajectoryWork` | Per trimmed rep, from `@ground-truth/physics`, with the optional constant device force. |

### Refusal reasons and thresholds

Every threshold is a named, exported constant. All are judgement calls except where
noted. `visibilityThreshold` and `maxGapS` can be passed in `SessionOptions` (defaults
unchanged).

| Reason | Refused when | Constant |
|---|---|---|
| `NO_SCALE` | `metersPerUnit` is `null` | |
| `LOW_FRAME_RATE` | median frame rate < 20 Hz, or the timestamps are so irregular that the grid would hold over 4 samples per delivered frame, or `cutoffHz` is at or above half the median frame rate | `MIN_RATE_HZ` |
| `LANDMARK_LOST` | more than 10 % of frames have visibility < 0.5 (or a non-finite `wristY`), or more than 10 % were dropped for their timestamps | `MAX_LOW_VISIBILITY_FRACTION`, `VISIBILITY_THRESHOLD` |
| `GAP_TOO_LONG` | more than 0.25 s between usable frames | `MAX_GAP_S` |
| `TOO_SHORT` | recording under 1.0 s, or no longer than the filter padding (`ceil(3·rate/cutoff)` samples, 90 at 60 Hz with a 2 Hz cutoff) | `MIN_DURATION_S`, `PADDING_CUTOFF_PERIODS` |
| `NO_REPS` | no complete repetition found: the wrist never rose and came back down by `minPhaseDisplacementM`, 0.10 m by default (held still, or lifted and never lowered) | `MIN_PHASE_DISPLACEMENT_M` |

`MIN_RATE_HZ` is 20, under every nominal camera rate (23.976, 24, 25, 29.97, 30): a
median of measured timestamps lands a hair either side of a nominal rate, so no
threshold may sit on one.

Gaps are measured between *usable* frames: the time from one visible frame to the next.
A run of `k` lost frames at rate `r` is a gap of `(k + 1) / r`, a hole in the timestamps
is its own width, and time lost before the first or after the last visible frame counts
too. Reasons come back in the order of the `RefusalReason` union.

**A gap just under the limit is not free.** The refusal threshold only decides what is
bridged by linear interpolation; the bridge still costs accuracy where the signal is
curved. Measured in review on synthetic lifts, with the longest gap that is accepted:
a gap at the turnaround of a 0.5 s lift under-reads range of motion by 8.1 % at 60 Hz
and 5.1 % at 30 Hz; a gap at the acceleration peak of a 1 s lift over-reads peak force
by 6.1 %. Lower `maxGapS` if that matters more than keeping a marginal session.

### Confidence grades capture conditions, not accuracy

`provenance.confidence` is a function of the frame rate and the fraction of lost frames
and of nothing else: not scale, not depth, not the pose model's noise, not whether the
reps were clean. It was `HIGH` for a rep that read 121 % high and for a 3 % scale error.
It is therefore **capped at `MEDIUM`** while `VALIDATED_ON_REAL_VIDEO` is `false`, which
it is until the checks under "What only real video can settle" have been done. The
uncapped grade is exported as `gradeCaptureConditions`: `HIGH` at ≥ 45 Hz with ≤ 2 %
lost frames, `LOW` below 27 Hz or above 5 % lost frames, otherwise `MEDIUM`
(`HIGH_CONFIDENCE_*`, `LOW_CONFIDENCE_*`; the boundaries sit between the nominal rates,
so 29.97 and 30.3 grade alike, and 59.94 and 50).

### Rep window: what belongs to a rep

`segmentReps` cuts a rep from one minimum to the next, which on its own bills the whole
rest before it, a pick-up from the floor, or a set-down to the rep (the first version of
this package read a dumbbell picked up from the floor as 1.10 m and 108.5 J for a 0.5 m,
49.05 J curl, and rest noise added 7 to 19 % after a 10 s rest). `analyzeSession` trims
each rep on the **smoothed** position, to the movement between two pauses: one before
the top, where the lift starts, and one after it, where the lowering ends.

**What a pause is.** A run of at least `DWELL_MIN_S` = 0.3 s in which the smoothed
position spreads (highest minus lowest) no more than `DWELL_BAND_M` = 1.5 cm, and which

1. **lies below the movement**: its rest level is at least `minPhaseDisplacementM`
   (10 cm, the threshold the segmenter uses to call something a phase) under the rep's
   top. A pause *at* the top is never a boundary, however long: it stays inside the rep,
   between the lift and the lowering.
2. **is actually at rest**: the half of it away from the movement (the first half before
   a lift, the second half after a lowering) travels no more than `ONSET_TOLERANCE_M` =
   3 mm. Slow movement fits inside 1.5 cm for 0.3 s anywhere along its way; without this
   test it was read as a pause.

**Which pauses.** There may be several on each side of the top: the rest, a hesitation
half-way, the pause after a pick-up. *A rep starts from and returns to roughly the same
height*, so the two that bound it are **the pair whose rest levels agree**:

- A sticking point half-way up has no pause at its height on the way down. The rests at
  the bottom agree, so the rep is whole.
- A barbell racked at the shoulders and then pressed returns to the shoulders. The two
  pauses at the shoulders agree, so the press is the rep and the clean is not.
- A pick-up from the floor followed by a pause is matched by the return to that pause's
  height, so the pick-up is not part of the first rep (nor the set-down of the last).
- A rep that does not come back to where it started has one height on each side and
  simply uses them.

Agreement is judged to `DWELL_BAND_M`: the pair with the smallest difference in level
is the best, every pair within 1.5 cm of it agrees equally, and of those the **smallest
window** wins (the latest start with the earliest end). The tolerance is needed because
the levels inside one rest differ by fractions of a millimetre once there is noise, and
an exact minimum then falls on an arbitrary instant deep inside the rests, billing them
to the rep (measured at ±2 mm with 10 s rests: start up to 8.9 s early, work +7.8 %).

**One candidate per rest level.** Before the pair is chosen, the pauses on each side of
the top are grouped by level: a gap of more than `SAME_REST_LEVEL_M` = 3 cm (twice the
band) separates two groups, and only the pause nearest the top in each group is a
candidate. Two pauses at nearly the same level on the same side are the same rest seen
twice; reaching for the outer one would add rest to the rep and no movement. A hand
that sways while it rests leaves scattered pauses at levels further apart than the
agreement band, and without the grouping the matching reached for a distant pair that
happened to agree. The price is that a stop within 3 cm of the rest's height *is* the
rest (see the failure modes).

**Never behind the last return to the rest level.** On each side the boundary cannot
lie further out than the last sample before the top (first after it) that is within
3 mm of the lowest level on that side: the position came back to the rep's lowest point
there, so nothing beyond it belongs to the rep. That sample is also the boundary on a
side with no pause at all (reps with no rest between them, a lowering that runs
straight into the set-down, a rest that wobbles by more than 1.5 cm and so holds no
pause). The segmenter's own boundary is the *first* lowest sample of the rest, which in
a wobbling rest is an arbitrary trough, often the first.

**Where in the pause the boundary goes.** The 1.5 cm band only *detects* the pause: a
run stays inside it until the movement has already travelled up to 1.5 cm. The pause's
**rest level** is the median of its still half, and the lift starts at the last sample
of the pause within `ONSET_TOLERANCE_M` of that level (the lowering ends at the first).
`ONSET_TOLERANCE_M` is a judgement call sized to the residual noise of the smoothed
signal (a few tenths of a millimetre for ±2 mm input noise, about 1 mm for ±5 mm).

Work, peak force, impulse, `pathLengthM`, `startS`, `durationS` and `rangeOfMotionM` are
all computed on the trimmed window. **`liftDurationS`** runs from the start to the *first*
sample within 3 mm of the top's level, so a pause at the top is not part of the lift.
**`trimmedRangeFraction`** is the range of motion measured divided by the range the
segmenter saw for that rep (its top minus the lower of its two ends): about 1 for a rep
between two rests, 0.45 for a 0.5 m curl after a 0.6 m pick-up, and low when slow
movement was trimmed as rest. It has no threshold and raises no flag; a consumer can
show "this rep was measured over 45 % of the detected movement".

All three constants are judgement calls, none tuned to a scenario, and each is held by
a test that fails if it is halved and one that fails if it is doubled.

#### Residual bias on ordinary reps (measured, synthetic)

0.5 m, 1 s minimum-jerk lift, 1 s lowering: the first and last 3 mm of the movement are
judged rest, which a minimum-jerk lift takes 0.08 s to cover. **Work −0.5 %, range of
motion −0.4 %** (−0.8 % and −0.7 % at 0.25 m). `startS` reads **0.07 to 0.10 s late**
at ±2 mm (0.02 to 0.12 s at ±5 mm) and `durationS` **0.13 to 0.18 s short** for a 2 s rep
(0.08 to 0.20 s at ±5 mm; the tests hold 0.135 s and 0.22 s over 30 seeds). `liftDurationS`
reads **0.85 s for a 1 s lift** (0.83 to 0.88 s over 100 seeds at ±2 mm, with or without a
pause at the top). A real lift is not minimum-jerk, so these are the bias of the method
on an idealised profile, not a prediction.

#### Tempo limits: slow movement (measured, synthetic)

Anything slower than `ONSET_TOLERANCE_M` in half of `DWELL_MIN_S`, about **2 cm/s**, is
a rest to test 2. That floor is inherent to the rule. The slow first and last
centimetres of a slow rep are therefore trimmed with the rests, and the loss grows as
the movement gets slower and shorter. Loss of work for a minimum-jerk lift and lowering
of the same duration, 3 s rests, 60 Hz (positive work, negative work and range of
motion agree to 0.1 point; `trimmedRangeFraction` reads one minus the loss):

| Height | 1 s per phase | 2 s | 4 s | 6 s | 8 s |
|---|---|---|---|---|---|
| 0.15 m, no noise | −1.3 % | −2.7 % | −5.5 % | −9.5 % | **−15.0 %** |
| 0.25 m, no noise | −0.8 % | −1.3 % | −2.7 % | −4.2 % | −6.1 % |
| 0.5 m, no noise | −0.5 % | −0.5 % | −1.1 % | −1.5 % | −2.2 % |
| 0.15 m, ±2 mm (worst of 20 seeds) | −2.8 % | −3.7 % | −7.0 % | −13.8 % | **−31.8 %** |
| 0.25 m, ±2 mm | −1.4 % | −1.9 % | −3.7 % | −5.5 % | −10.3 % |
| 0.5 m, ±2 mm | −0.7 % | −0.8 % | −1.3 % | −2.1 % | −3.2 % |
| 0.15 m, ±5 mm (worst of 20 seeds) | −3.4 % | −5.7 % | −10.2 % | **−31.7 %** | **−28.2 %** |
| 0.25 m, ±5 mm | −2.5 % | −1.8 % | −4.9 % | −11.7 % | −15.4 % |
| 0.5 m, ±5 mm | −1.2 % | −0.9 % | −1.5 % | −2.5 % | −5.1 % |

(The rule this replaced read −84 to −96 % in six of the fifteen no-noise cells: from
4 s at 0.15 m, 6 s at 0.25 m and 8 s at 0.5 m.) **A 0.15 m movement taking 6 s or more
per phase loses up to a third of its work once there is noise**, with
`trimmedRangeFraction` at 0.63 to 0.85 as the only sign. Its peak speed is 3.5 to
4.7 cm/s, barely above the floor. The timing errors grow the same way: a 0.5 m lift of
2, 4 and 8 s starts 0.17, 0.43 and 1.12 s late and its rep reads 0.33, 0.87 and 2.23 s
short.

When only one half is slow (0.2 m, 1 s one way and 5 s the other) the fast half reads
−1.4 % and the slow half −4.7 % (to −6.6 % at ±2 mm and −12.2 % at ±5 mm over 20 seeds).

Constant-speed movement has no fast middle, so it shows the floor directly. Up and down
0.3 m at a constant speed, 3 s rests, work:

| Speed | No noise | ±2 mm (worst of 20 seeds) | ±5 mm |
|---|---|---|---|
| 12 cm/s | −0.9 % | −1.0 % | −0.5 % |
| 8 cm/s | −1.3 % | −0.9 % | −0.3 % |
| 5 cm/s | −1.3 % | −1.5 % | −1.2 % |
| 3 cm/s | −1.7 % | **−67.0 %** | **−67.1 %** |
| 2 cm/s | **−67.7 %** | **−67.4 %** | **−65.7 %** |

Below the floor the rep collapses to the last 10 cm under the top (`trimmedRangeFraction`
0.32 here; −80 % over 0.5 m). **With noise the floor for constant-speed movement is
between 3 and 5 cm/s.** (The previous rule collapsed at 5 cm/s and below, to −91 to −97 %.)

#### Known failure modes of the pair-matching rule (measured, synthetic)

- **A stop on the way up *and* one at the same height on the way down** is a rack as far
  as this rule can tell: only the part above them is measured (0.35 s stops at 0.25 m in
  a 0.5 m rep: range of motion and both works −50 %, `trimmedRangeFraction` 0.50). Stops
  at different heights (0.25 m up, 0.15 m down) do not match, and the rep is whole.
- **A stop on the way up in a rep that does not return to its start height** wins if it
  is nearer the return height than the start is (stop at 0.25 m, return to +0.15 m:
  range of motion and positive work −50 %, `trimmedRangeFraction` 0.50).
- **A stop within 3 cm of the rest's height is the rest.** The rep starts (or ends) at
  the stop and reads that much short. A 0.6 s stop above the start height, on the way
  down: 1 cm above, negative work −2.1 to −2.5 %; 2.5 cm above, −5.1 to −5.6 %; 5 cm
  above, the stop is its own level, has no match on the way up, and the rep runs on to
  the rest (−0.3 to +0.3 %). The same on the way up costs positive work and range of
  motion (3 cm above: −6.1 to −6.5 %). Durations follow: 1.83 s instead of 2.85 s.
- **A hand that sways or wobbles while it rests.** Sinusoids added to the whole
  recording, 0.5 m reps of 1 s up and 1 s down (clean `durationS` 1.83 s). **Amplitude
  is half the peak-to-peak.** The numbers depend on where in the oscillation the lift
  begins, so each cell is the range over eight phases and three reps:

  | Oscillation | Positive work | `durationS` | Peak force |
  |---|---|---|---|
  | sway 1 cm amplitude at 0.2 Hz, 5 s rests | −3.0 to +2.3 % | 1.80 to 1.90 s | |
  | sway 2 cm amplitude at 0.2 Hz | −5.6 to +5.4 % | 1.80 to **3.02 s** | |
  | sway 3 cm amplitude at 0.2 Hz | −6.6 to +10.5 % | 1.97 to **4.30 s** | |
  | wobble 0.5 cm amplitude at 1.5 / 2.5 / 3 Hz, 4 s rests | ±1.6 / ±1.5 / −1.2 to +1.7 % | to 2.4 / 2.2 / 2.2 s | to +3.2 / +8.3 / +10.5 % |
  | wobble 1 cm amplitude at 1.5 Hz, rests of 1, 4 and 10 s | −3.2 to +4.6 % | 1.90 to 2.50 s | −0.9 to +6.6 % |
  | wobble 1 cm amplitude at 2.5 Hz | +2.4 to +3.5 % | 1.93 to 2.33 s | +6.6 to +16.7 % |
  | wobble 1 cm amplitude at 3 Hz | +1.5 to +4.6 % | 1.93 to 2.23 s | +16.2 to +20.9 % |
  | wobble 1 cm at 1.5 / 2.5 / 3 Hz with ±2 mm noise on top | to +5.2 / +5.8 / **+11.3 %** | to 2.52 / 2.33 / **2.90 s** | |
  | wobble 1.5 cm amplitude at 1.5 / 2.5 Hz | to +8.4 / +8.8 % | to 2.5 / 2.3 s | |
  | wobble 1.5 cm amplitude at 3 Hz | to **+59.9 %** | to **6.0 s** | |

  The work error of a sway is the sway's own travel under the lift and is there whatever
  the rule. What the rule adds is the duration: with a 2 cm sway the hand moves faster
  than the 2 cm/s floor as the lift begins, so the nearest pause can be up to half a
  second back, and beyond that amplitude the swaying rest stops being one level. A wobble
  rides on the lift, so its work error and above all its peak-force error are real
  movement that the 4 Hz filter passes; it no longer pulls the rest into the rep, except
  at 1.5 cm amplitude and 3 Hz, where it still does. (For scale: before the grouping and
  the return bound, the 1 cm wobble at 2.5 Hz read +17 % and 4.0 s after 1 s rests, +74 %
  and 10 s after 4 s rests, +178 % and 22 s after 10 s rests; the rule before pair
  matching read +8.9 % and 2.6 s there, and +38 % / 6 s at 3 Hz.) A drift of 1 cm/s during
  5 s rests, or a hand that rises or sinks 2 cm in the rest and returns 1 cm off, stays
  within 1.2 % and 0.2 s.
- **A rep that does not return to its start height, with an earlier pause at the return
  height** still inside the segmenter's rep: the window is extended back to that pause.
- **No pause before the set-down or after the pick-up**: see "Capture protocol".
- A **sub-threshold movement** (under 10 cm) between two reps is attributed to neither
  rep when a pause separates it from each of them (a 0.08 m partial between two full
  reps, with 0.6 s pauses either side, leaves both reps within 0.8 % at ±2 mm). When no pause
  separates it from a rep it stays in that rep and its work is added to it.
- **Reps with no rest between them**: the turnaround at the bottom is borderline for a
  pause when a lift is about 1 s. Pause or not, the boundary falls 3 mm into the movement
  either side of the lowest sample: work within 0.6 % at ±2 mm and 1.0 % at ±5 mm, start
  0.03 to 0.10 s late.
- **`liftDurationS` at ±5 mm with a pause at the top**: the top's level is the highest
  sample of a noisy plateau, and a 1 s lift then reads up to 1.15 s (0.85 s without
  noise); one 0.4 s lift in a hundred read over the `filterLimited` threshold. At ±2 mm
  it holds to one sample over 100 seeds.

### Behaviour worth knowing

- **Segmentation is displacement hysteresis, not velocity sign changes.** A turning
  point is confirmed only once the position has moved back by at least the threshold
  from it, so a 5 cm dip half-way up a lift does not split it and ±3 mm jitter makes no
  rep. A rep is a minimum, the next maximum and the next minimum. A lift with no
  lowering is not a rep, and a movement that begins mid-lowering is ignored.
- **A recording that starts mid-lift** is counted as a rep for the part that is visible,
  and one that **stops mid-lowering** ends its last rep at the last sample if the lowering
  has already passed the threshold. Work, range of motion and duration are then partial.
  One that stops before that (at the top, or under 0.10 m into the lowering) loses that
  last lift; a recording with no other repetition is then refused `NO_REPS`.
- **`startS`** is measured from the first frame of the recording (the first with a usable
  timestamp), so a clock that starts at 123456.789 s changes nothing.
- **Edge padding** is a point reflection about the end sample (`2·x₀ − xⱼ`), three
  cutoff periods long, with the filter started in its steady state: a constant input
  comes out unchanged to the last sample, and a trace that starts mid-lift keeps its first
  sample within 1 mm (a mirror reflection is 26.6 mm out). It needs more samples than the
  padding (46 at 60 Hz and 4 Hz).

### Fast lifts: the filter, `filterLimited`, and what 4 Hz means

The default cutoff is 4 Hz at the **−6 dB point of the two-pass filter** (gain exactly
0.5 at 4 Hz). Its −3 dB point is `0.802 × fc` ≈ 3.2 Hz. The default suits lifts of about
0.8 s or slower; a faster lift is shaped by the filter. Each rep reports
`filterLimited: true` when `liftDurationS` is under `FILTER_LIMITED_LIFT_S` = 0.65 s.
`liftDurationS` leaves out the first and the last 3 mm of the lift, so it reads about
15 % under the full time of a 0.5 m lift (measured: 1.0 s reads 0.850, 0.9 s 0.767, 0.8 s
0.683, 0.75 s 0.650, 0.7 s 0.617, 0.6 s 0.533): **0.65 s is a 0.5 m lift of about 0.75 s**,
and a 0.8 s lift, which the table below shows within half a percent, is not flagged. A
shorter movement reads shorter still, because 3 mm is a larger share of it (1.0 s over
0.25 m reads 0.800 s, over 0.15 m 0.767 s), so the flag fires under about 0.8 s at 0.25 m
and 0.85 s at 0.15 m. (The constant was 0.7 while `liftDurationS` ran to the top sample
and read 8 % under; at 0.7 it would now flag 0.8 s lifts.)

Filter bias on a 0.5 m lift with zero noise at 60 Hz, 4 Hz cutoff, **measured in review
on synthetic signals, before the rep window was trimmed** (signed, against the rep's
true value):

| Lift time | Work | Peak force | Range of motion (pre-ringing) |
|---|---|---|---|
| 1.0 s | +0.37 % | −0.01 % | +0.27 % |
| 0.8 s | +0.65 % | −0.37 % | |
| 0.6 s | +1.30 % | −1.98 % | +0.94 % |
| 0.4 s | −5.92 % | −10.51 % | +1.99 % |
| 0.4 s at 30 Hz | −9.05 % | −10.90 % | |

A faster cutoff recovers the 0.4 s lift: with 6 Hz it reads −2.3 % work and −3.3 % peak
force, with 8 Hz −1.2 % and −0.9 % (review; noise rises with the cutoff, so raise it
only for lifts that need it). The zero-phase filter rings slightly *before* a lift that
starts from rest, so a lift that is not trimmed would read its range of motion high: a
few tenths of a percent for a ~1 s lift (+0.27 %), and 0.94 % and 1.99 % at 0.6 s and
0.4 s.

The same lifts after the window trim, measured by the tests' scenarios against a 2000 Hz
reference of the same rep (the 1.0 s row's −0.5 % is the window residual above, not the
filter; unchanged by the pair-matching rule):

| Lift time | Work | Peak force | Range of motion |
|---|---|---|---|
| 1.0 s | −0.46 % | −0.01 % | −0.37 % |
| 0.8 s | −0.41 % | −0.37 % | −0.26 % |
| 0.6 s | +0.34 % | −1.98 % | +0.47 % |
| 0.4 s | −8.21 % | −10.51 % | +1.19 % |

The 0.4 s row is pinned by a test (work −8.2 % and peak −10.5 %, each ±1 point), which
also pins the default cutoff at 4 Hz. (With the boundary at the pause's edge the
rows read −3.15, −3.17, −3.32 and −9.69 % work, and −2.55, −2.30, −1.89 and +0.18 %
range of motion.)

## Measured errors (synthetic, not real video)

Every number below was measured with the scenarios of `test/session.test.ts`,
`test/window.test.ts` and `test/rep-window.test.ts` on **synthetic sessions**: a 10 kg
load, 0.5 m minimum-jerk lifts of 1 s with 1 s lowerings and 0.5 s rests (5 s and 10 s in
the rows that say so), Earth gravity, positions with uniform ±noise from a seeded
generator (`test/helpers.ts`). The pose model, a real camera and a real arm are not in
the loop, so these are lower bounds on what real video will do. Truth per rep: positive
work 49.05 J, peak force 126.97 N, range of motion 0.5 m. Errors are the largest over the
reps (and seeds) of the session, signed as measured minus truth. This table was
regenerated after the pauses that bound a rep came to be chosen by matching rest levels;
for these ordinary reps the numbers moved by a few hundredths of a point at most (the
boundary inside a pause is placed as before), and the four sticking-point rows read
−50 % in work or range of motion under the previous rule.

| Scenario | Reps | Work | Peak force | Range of motion | Confidence (uncapped) |
|---|---|---|---|---|---|
| 60 Hz, no noise | 3 | −0.46 % | −0.01 % | −0.37 % | MEDIUM (HIGH) |
| 60 Hz, ±2 mm (seed 1) | 3 | −0.47 % | +1.27 % | −0.36 % | MEDIUM (HIGH) |
| 60 Hz, ±2 mm (five seeds, worst) | 3 | −0.73 % | +2.58 % | −0.65 % | MEDIUM (HIGH) |
| 30 Hz, ±2 mm | 3 | −0.36 % | +2.02 % | −0.33 % | MEDIUM (MEDIUM) |
| 60 Hz, ±5 mm (seed 1) | 3 | −0.66 % | +3.42 % | −0.53 % | MEDIUM (HIGH) |
| 60 Hz, ±5 mm (seed 2) | 3 | −0.42 % | +6.72 % | −0.35 % | MEDIUM (HIGH) |
| 60 Hz, ±2 mm, 4 % of frames lost | 3 | −0.47 % | +1.47 % | −0.36 % | MEDIUM (MEDIUM) |
| 5 reps, ±2 mm (seeds 3, 17, 99; worst) | 5, 5, 5 | −0.73 % | +2.34 % | −0.65 % | MEDIUM (HIGH) |
| 5 s rests, ±2 mm (30 seeds, worst) | 3 | −0.62 % | +2.97 % | −0.54 % | MEDIUM (HIGH) |
| 5 s rests, ±5 mm (30 seeds, worst) | 3 | −0.83 % | +7.54 % | −0.76 % | MEDIUM (HIGH) |
| 10 s rests, ±2 mm (30 seeds, worst) | 3 | −0.72 % | +3.70 % | −0.56 % | MEDIUM (HIGH) |
| 10 s rests, ±5 mm (30 seeds, worst) | 3 | −1.11 % | +9.38 % | −0.79 % | MEDIUM (HIGH) |
| Floor pick-up, pause, 3 curls, set-down, ±2 mm (10 seeds, worst) | 3 | −0.55 % | +2.46 % | −0.47 % | MEDIUM (HIGH) |
| Rack to shoulders, 2 presses, un-rack, ±2 mm (10 seeds, worst) | 2 | −0.57 % | +2.12 % | −0.45 % | MEDIUM (HIGH) |
| 0.08 m partial between 2 reps, ±2 mm (10 seeds, worst) | 2 | −0.51 % | +2.27 % | −0.42 % | MEDIUM (HIGH) |
| 0.2 s stop half-way up, ±2 mm (10 seeds, worst; peak vs 155.8 N) | 1 | +0.58 % | −3.84 % | −0.24 % | MEDIUM (HIGH) |
| 0.35 s stop half-way up, ±2 mm (10 seeds, worst) | 1 | +0.62 % | −3.49 % | −0.37 % | MEDIUM (HIGH) |
| 0.2 s stop half-way down, ±2 mm (10 seeds, worst) | 1 | +0.60 % | −3.82 % | −0.36 % | MEDIUM (HIGH) |
| 0.35 s stop half-way down, ±2 mm (10 seeds, worst) | 1 | +0.68 % | −3.51 % | −0.36 % | MEDIUM (HIGH) |
| ISS, 1000 N device force, ±2 mm (vs 500 J, 1028.9 N) | 3 | −0.37 % | +0.16 % | −0.36 % | MEDIUM (HIGH) |
| Scale 3 % too large, no noise | 3 | +2.53 % | +0.67 % | +2.62 % | MEDIUM (HIGH) |
| Scale 3 % too large, ±2 mm | 3 | +2.80 % | +1.99 % | +2.86 % | MEDIUM (HIGH) |
| 0.25 m rep, 5 s rests, no noise (vs 24.525 J, 112.5 N) | 3 | −0.81 % | −0.01 % | −0.73 % | MEDIUM (HIGH) |

The sticking-point rows are 0.25 m legs of 0.5 s, whose peak force the 4 Hz filter
flattens by 3.5 %. Slow tempos are in "Tempo limits" above, not in this table.

The two scale rows are the scale error plus the window residual: +3 % in scale is +3 % in
work and range of motion (the tests assert it against the uncorrected session), less the
0.5 % the trimmed window leaves out. (While the boundary sat at the pause's edge the
window residual was −3 %, which cancelled the scale error on a 0.5 m rep and made the
rows read −0.26 % and +0.67 %; that was a coincidence of sizes, not scale error cancelling.)

The test assertions for the scenarios with rests, pick-ups and sticking points hold about
twice the worst value measured over 10 to 30 seeds (work within 1.1 to 2.2 %); the
noise scenarios of the first rows keep the plan's wider targets (work within 2 to 10 %,
peak within 3 to 10 %).

**Peak force is the noisiest output.** Over 200 seeds the worst peak-force error was
**3.37 % at ±2 mm and 8.72 % at ±5 mm** (measured in review, reproduced with the current
rep window; work and range of motion worst 0.77 % and 0.69 % at ±2 mm, 1.28 % and 1.11 %
at ±5 mm). White noise is the optimistic case: real pose-model error is correlated in time.
A wobble of 1 cm amplitude at 2.5 Hz — inside the pass band — measures +2.4 to +3.5 % work
and +6.6 to +16.7 % peak force over eight phases with the current rep window (the table
under "Known failure modes" has the other frequencies and amplitudes), so the table above
is a lower bound on the error of real video. The plan's ISS expected value is `1000 × 0.5 J` plus a kinetic term; for a
minimum-jerk lift that term is zero, because the ½ m v² borrowed while accelerating is
returned while braking inside the same lift and no interval changes sign (the derivation
is in the test).

## Scale

Metres-per-unit is set by the entered stature and the eye and ankle landmarks of a
calibration frame, through the proportion `EYE_TO_ANKLE_FRACTION_OF_STATURE` = 0.897.
**A scale error is passed straight through: 3 % in scale is 3 % in work and in range of
motion**, and nothing downstream can detect it. That proportion is an **ANTHROPOMETRIC
ESTIMATE — verify against the source before the hackathon.** It is eye height 0.936·H
minus ankle height 0.039·H (Drillis & Contini segment proportions, as tabulated in
Winter, *Biomechanics and Motor Control of Human Movement*), quoted from memory of the
table and not yet checked.

Error budget of the stature method. **These are the reviewer's estimates, not measured
here**:

- Body proportion (the 0.897), landmark placement, self-reported stature and posture each
  contribute about 1 %.
- **Depth is the dominant term.** Scale is proportional to distance from the camera, but
  the stature method scales the body's mid-plane, and the near wrist in a side-on pose is
  roughly 0.15–0.25 m closer to the camera than that. At 2.5 m that is about **+6 to
  +10 % on range of motion and work**. A 10 cm step toward the camera after calibration
  is another 4 %.
- Realistic total: **±5–10 % with a positive bias**.

`metersPerUnitFromKnownLength(lengthM, yA, yB)` = `lengthM / |yB − yA|` is the preferred
calibration: hold an object of known length vertically in the lifting hand, at the wrist's
depth, and read its two ends in one frame. It removes the depth term, because the
reference is at the wrist's own distance (it throws when the span is under 0.05 of the
frame). Whichever method is used, check scale end to end with a **tape-measured rep**
before trusting a number (see below). All of this section is an estimate until that has
been done.

## What this package does not do

- No camera and no pose model: it takes plain `PoseFrame` objects, and the adapter that
  produces them ships with the demo.
- No object detection. **The wrist stands in for the load.** A barbell that swings away
  from the wrist, or a cable that is not in the hand, is not measured.
- 2D only. The movement must be side-on to the camera; out-of-plane motion reads as
  less range of motion.
- Free weights and a constant device force only (`deviceForceN`). Variable-resistance
  devices, bands and flywheels are not modelled.
- No loading rate, no per-joint kinematics, no multi-person frames.
- **No real-video validation.** Everything above is synthetic.

### Limits that follow from the method

- **Phantom reps from sway.** The 0.10 m threshold is absolute. A stationary arm with a
  slow sway can cross it: measured, a 6 cm sway at 0.25 Hz gives two 0.12 m reps.
- **A recording that starts mid-lift** counts the visible part as a rep.
- **White noise is the optimistic case** for the error table (see above): a wobble of
  1 cm amplitude at 2.5 to 3 Hz passes the filter and measures up to +4.6 % work and
  +16.7 to +20.9 % peak force; at 1.5 cm amplitude and 3 Hz it still pulls the rest into
  the rep (+60 %).
- **A stop within 3 cm of the rest's height is the rest**, and a sway of 2 cm amplitude
  or more stretches a rep's duration (see "Rep window").
- **Slow movement is trimmed as rest** below about 2 cm/s (3 to 5 cm/s with noise), a
  stop at the same height on both sides of the top reads as a rack, and a sub-threshold
  movement that no pause separates from a rep stays in it (see "Rep window").
- **Phone-camera pitch and height** are not modelled; the movement is assumed to be in a
  plane facing the camera.

## What only real video can settle

Ten checks that no synthetic test can stand in for. `VALIDATED_ON_REAL_VIDEO` stays
`false` (and confidence stays capped) until they are done.

1. **Scale, end to end:** a tape-measured rep at two distances and with both arms, against
   `rangeOfMotionM`. This is the only way to see the depth term.
2. **The pose model's noise spectrum:** a motionless 20 s recording; look for content at
   1–4 Hz, which the filter passes.
3. **Wrist visibility through a full rep,** near the face, and when the dumbbell
   occludes the hand.
4. **Delivered frame timing on the demo phone:** the actual rate, duplicates, and whether
   timestamps are capture time or callback time.
5. **Whether the wrist landmark slides** along the forearm as the wrist rotates.
6. **The real pick-up / pre-roll / set-down sequence,** to see whether the pause rule
   isolates the reps as it does on synthetic ones, and **how far a resting hand really
   drifts, sways and trembles**: the rule takes two pauses within 3 cm on one side of the
   top for the same rest, and a rest that wobbles more than 1.5 cm holds no pause at all.
7. **A known mass through a measured height** at slow, normal and fast tempo, against
   `m·g·h`. Slow is where the synthetic limit is (see "Tempo limits").
8. **Camera pitch (about 15°) and height:** how much each reads as lost range of motion.
9. **Rep counting on an uneven real set** with a failed last rep.
10. **Peak-force plausibility against a second instrument** (a force plate or an
    accelerometer on the bar). Until then present peak force as indicative only.
