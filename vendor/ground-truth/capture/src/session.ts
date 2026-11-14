/**
 * Session analysis: noisy wrist positions in, per-repetition work, peak force and range
 * of motion out, or a refusal with reason codes.
 *
 * Pipeline: assessQuality → refuse if any reason → resampleUniform → toMetersUp →
 * lowPassZeroPhase → segmentReps → trim each rep to its movement → trajectoryWork per rep.
 */

import { trajectoryWork, type Confidence, type Provenance } from "@ground-truth/physics";
import type { PoseFrame } from "./frames";
import { DEFAULT_CUTOFF_HZ, filterPaddingSamples, lowPassZeroPhase } from "./filter";
import { assessQuality, resampleUniform, type QualityOptions, type QualityReport, type RefusalReason } from "./quality";
import { requireFinite } from "./internal";
import { toMetersUp } from "./scale";
import { MIN_PHASE_DISPLACEMENT_M, segmentReps, type Rep } from "./segment";

/**
 * Judgement call: HIGH confidence needs a frame rate of at least this. The grade
 * thresholds sit between the nominal camera rates (30 / 29.97 fps, 50 / 59.94 / 60 fps),
 * never on one, so a measured 29.97 and a nominal 30 grade alike.
 */
export const HIGH_CONFIDENCE_MIN_RATE_HZ = 45;
/** Judgement call: HIGH confidence allows at most this fraction of low-visibility frames. */
export const HIGH_CONFIDENCE_MAX_LOW_VISIBILITY = 0.02;
/** Judgement call: a frame rate below this is LOW confidence. */
export const LOW_CONFIDENCE_BELOW_RATE_HZ = 27;
/** Judgement call: more than this fraction of low-visibility frames is LOW confidence. */
export const LOW_CONFIDENCE_ABOVE_LOW_VISIBILITY = 0.05;

/**
 * Judgement call: a pause is a run of at least this long (seconds) in which the smoothed
 * position stays within DWELL_BAND_M. It separates the movement of a rep from the rest,
 * pick-up or set-down around it. Not tuned to any one scenario; see "Rep window" below.
 * Half of it is also the stretch over which a pause must be still (ONSET_TOLERANCE_M), so
 * it sets the speed floor: ONSET_TOLERANCE_M / (DWELL_MIN_S / 2) = 2 cm/s.
 */
export const DWELL_MIN_S = 0.3;
/**
 * Judgement call: the largest spread (highest minus lowest sample) of the smoothed
 * position inside a pause, metres. 1.5 cm is above the smoothed pose noise at rest
 * (a few millimetres) and below the 10 cm rep threshold. It only DETECTS pauses: a run
 * stays inside this band until the movement has already travelled up to 1.5 cm, so the
 * rep boundary is not placed at the pause's edge but at the rest level (ONSET_TOLERANCE_M).
 * It is also how closely two rest levels must agree to count as the same height when the
 * pauses that bound a rep are chosen.
 */
export const DWELL_BAND_M = 0.015;
/**
 * Judgement call: how far from a pause's rest level (metres) a sample may be and still be
 * rest. It is sized to the residual noise of the smoothed signal, a few tenths of a
 * millimetre for ±2 mm input noise and about 1 mm for ±5 mm, with margin for the filter's
 * pre-ringing; it is not tuned to any scenario. The lift starts at the last pause sample
 * within this of the level, the lowering ends at the first, and the lift is over (for
 * `liftDurationS`) at the first sample within this of the top. A min-jerk lift of 0.5 m in
 * 1 s covers 3 mm in 0.08 s, so the onset still reads a little late (about 0.6 % of that
 * range of motion is left out at each end). It is also the most the still half of a pause
 * may travel.
 */
export const ONSET_TOLERANCE_M = 0.003;

/**
 * Measured in the physics review and in this package's review, on synthetic lifts at the
 * default 4 Hz cutoff: a lift shorter than about 0.77 s is shaped by the filter (work and
 * peak force read low, range of motion high; see the README table). The flag compares this
 * constant with `liftDurationS`, which leaves out the first and the last ONSET_TOLERANCE_M of
 * the lift and so reads about 15 % under the full time of a 0.5 m lift (measured: 1.0 s reads
 * 0.850, 0.9 s 0.767, 0.8 s 0.683, 0.75 s 0.650, 0.7 s 0.617, 0.6 s 0.533): 0.65 s here is a
 * lift of about 0.75 s. It was 0.7 while `liftDurationS` ran from the onset to the top sample
 * (which read 8 % under); left at 0.7 it would flag the 0.8 s lifts the README table shows
 * are within half a percent. A shorter movement reads shorter still (3 mm is a larger share
 * of it: 1.0 s over 0.25 m reads 0.800, over 0.15 m 0.767).
 */
export const FILTER_LIMITED_LIFT_S = 0.65;

/**
 * False until the pipeline has been checked against real video (a tape-measured rep, a
 * known mass through a measured height). While it is false the confidence grade is capped
 * at MEDIUM: the grade describes CAPTURE CONDITIONS (frame rate, lost frames), not accuracy,
 * and it was HIGH for a rep that read +121 % and for a 3 % scale error.
 */
export const VALIDATED_ON_REAL_VIDEO = false;

export interface SessionOptions extends QualityOptions {
  massKg: number;
  gEnvMs2: number;
  /** Metres per normalised image unit (see metersPerUnitFromStature), or null if no calibration was done. */
  metersPerUnit: number | null;
  /** Constant device force resisting upward motion (e.g. an ARED setting). Default 0. */
  deviceForceN?: number;
  cutoffHz?: number;
  minPhaseDisplacementM?: number;
  // visibilityThreshold and maxGapS (from QualityOptions) move the quality gate's limits; the defaults are VISIBILITY_THRESHOLD and MAX_GAP_S.
}

export interface RepResult {
  startS: number; // seconds from the first frame of the recording to the movement onset (where the position leaves the rest level before the lift)
  durationS: number; // movement onset to movement offset (where the position reaches the rest level after the lowering)
  /**
   * Movement onset to the first sample within ONSET_TOLERANCE_M of the top's level: the lift alone, without
   * any pause at the top. (The top itself is the highest sample of the plateau, which noise places anywhere
   * in a pause.) It leaves out 3 mm at each end, so a 1 s lift of 0.5 m reads 0.85 s.
   */
  liftDurationS: number;
  /** True when liftDurationS is under FILTER_LIMITED_LIFT_S: the 4 Hz default cutoff shapes a lift this fast, so work and peak force read low. */
  filterLimited: boolean;
  rangeOfMotionM: number; // height of the lift, smoothed top minus smoothed onset
  pathLengthM: number; // distance travelled inside the rep window, up and down (Σ |Δy|): about twice rangeOfMotionM for a rep that returns to its start
  /**
   * How much of the movement the segmenter detected was measured: rangeOfMotionM divided by the segmenter's
   * range for this rep (its top minus the lower of its two ends). About 1 for a rep between two rests at the
   * same height; 0.45 for a 0.5 m curl that followed a 0.6 m pick-up from the floor (the pick-up is rightly
   * left out); low also when slow movement was taken for rest. No threshold and no flag: the number is the
   * information.
   */
  trimmedRangeFraction: number;
  positiveWorkJ: number;
  negativeWorkJ: number; // <= 0
  peakForceN: number;
  impulseNs: number;
}

/**
 * `provenance.confidence` grades the CAPTURE CONDITIONS (frame rate, lost frames), not the
 * accuracy of the numbers, and is capped at MEDIUM while VALIDATED_ON_REAL_VIDEO is false.
 */
export type SessionResult =
  | {
      ok: true;
      reps: RepResult[];
      totalPositiveWorkJ: number;
      maxPeakForceN: number;
      quality: QualityReport;
      provenance: Provenance;
    }
  | { ok: false; reasons: RefusalReason[]; quality: QualityReport };

/**
 * The grade of the CAPTURE CONDITIONS alone, before the real-video cap: frame rate and
 * lost frames. It says nothing about accuracy: scale, depth and the pose model's noise
 * are not in it.
 */
export function gradeCaptureConditions(quality: Pick<QualityReport, "rateHz" | "lowVisibilityFraction">): Confidence {
  if (quality.rateHz < LOW_CONFIDENCE_BELOW_RATE_HZ || quality.lowVisibilityFraction > LOW_CONFIDENCE_ABOVE_LOW_VISIBILITY) {
    return "LOW";
  }
  if (quality.rateHz >= HIGH_CONFIDENCE_MIN_RATE_HZ && quality.lowVisibilityFraction <= HIGH_CONFIDENCE_MAX_LOW_VISIBILITY) {
    return "HIGH";
  }
  return "MEDIUM";
}

/** The reported grade: the capture-conditions grade, capped at MEDIUM until VALIDATED_ON_REAL_VIDEO. */
function confidenceOf(quality: QualityReport): Confidence {
  const grade = gradeCaptureConditions(quality);
  return grade === "HIGH" && !VALIDATED_ON_REAL_VIDEO ? "MEDIUM" : grade;
}

/** True when the smoothed position stays within DWELL_BAND_M over samples a..b (inclusive). */
function isPause(y: readonly number[], a: number, b: number): boolean {
  let lo = y[a] as number;
  let hi = lo;
  for (let i = a + 1; i <= b; i++) {
    const v = y[i] as number;
    if (v < lo) lo = v;
    else if (v > hi) hi = v;
    if (hi - lo > DWELL_BAND_M) return false;
  }
  return true;
}

/** Median of y[from..to] (the mean of the middle two when the count is even). */
function median(y: readonly number[], from: number, to: number): number {
  const sorted = y.slice(from, to + 1).sort((p, q) => p - q);
  const mid = sorted.length >> 1;
  return sorted.length % 2 === 1 ? (sorted[mid] as number) : ((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2;
}

/** A pause that may bound a rep: the sample the boundary goes at, and the rest level it was placed by. */
interface Boundary {
  index: number;
  level: number;
}

/**
 * The pause y[last - run + 1 .. last] as the start of a lift, or null if it cannot be one. Its rest level is the
 * median of its first half, which the coming lift has not reached. It qualifies only if that level is at or
 * below `ceiling` (the pause lies below the movement, not on its top plateau) and the first half is actually
 * at rest (net travel within ONSET_TOLERANCE_M: slow movement fits inside DWELL_BAND_M for DWELL_MIN_S without
 * being a rest). The boundary is the last sample of the pause within ONSET_TOLERANCE_M of the level; if none
 * is that close (a level between two samples further apart than the tolerance) it is the pause's last sample.
 */
function onsetCandidate(y: readonly number[], last: number, run: number, ceiling: number): Boundary | null {
  const first = last - run + 1;
  if (first < 0 || !isPause(y, first, last)) return null;
  const halfEnd = first + (run >> 1) - 1;
  const level = median(y, first, halfEnd);
  if (level > ceiling) return null;
  if (Math.abs((y[halfEnd] as number) - (y[first] as number)) > ONSET_TOLERANCE_M) return null;
  for (let i = last; i >= first; i--) if (Math.abs((y[i] as number) - level) <= ONSET_TOLERANCE_M) return { index: i, level };
  return { index: last, level };
}

/** Mirror image of onsetCandidate: the pause is y[first .. first + run - 1], its level and its rest test use its SECOND half, and the lowering ends at its first sample within ONSET_TOLERANCE_M of the level (else at `first`). */
function offsetCandidate(y: readonly number[], first: number, run: number, ceiling: number): Boundary | null {
  const last = first + run - 1;
  if (last >= y.length || !isPause(y, first, last)) return null;
  const halfStart = last - (run >> 1) + 1;
  const level = median(y, halfStart, last);
  if (level > ceiling) return null;
  if (Math.abs((y[last] as number) - (y[halfStart] as number)) > ONSET_TOLERANCE_M) return null;
  for (let i = first; i <= last; i++) if (Math.abs((y[i] as number) - level) <= ONSET_TOLERANCE_M) return { index: i, level };
  return { index: first, level };
}

/**
 * Judgement call: two pauses on the same side of the top whose rest levels are within this of each other are
 * the same rest seen twice, and only the one nearer the top may bound the rep. Twice the band: a pause cannot
 * exist where the position spreads more than DWELL_BAND_M, so the pauses scattered through one wobbling rest
 * sit within about a band of each other, while a sticking point, a rack or a pick-up pause is far further
 * from the rest it could be confused with.
 */
export const SAME_REST_LEVEL_M = 2 * DWELL_BAND_M;

/**
 * `candidates` (innermost first) without those whose level is within SAME_REST_LEVEL_M of one already kept:
 * the innermost candidate of each rest level. An outer pause may replace an inner one only when reaching for
 * it adds real movement to the rep.
 */
function onePerRestLevel(candidates: readonly Boundary[]): Boundary[] {
  if (candidates.length === 0) return [];
  // group by level: sorted by level, a gap of more than SAME_REST_LEVEL_M starts a new group
  const order = candidates.map((_, i) => i).sort((p, q) => (candidates[p] as Boundary).level - (candidates[q] as Boundary).level);
  const innermost: number[] = []; // per group, the smallest position in `candidates` (innermost first)
  let previous = Number.NEGATIVE_INFINITY;
  for (const i of order) {
    const level = (candidates[i] as Boundary).level;
    if (level - previous > SAME_REST_LEVEL_M) innermost.push(i);
    else if (i < (innermost[innermost.length - 1] as number)) innermost[innermost.length - 1] = i;
    previous = level;
  }
  return innermost.sort((p, q) => p - q).map((i) => candidates[i] as Boundary);
}

/** First position in `sorted` (ascending) whose value is >= x. */
function lowerBound(sorted: readonly number[], x: number): number {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((sorted[mid] as number) < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * The pair of pauses that bounds the rep. `onsets` and `offsets` are not empty.
 *
 * The best agreement is the smallest difference between an onset level and an offset level. Every pair
 * whose levels differ by no more than that plus DWELL_BAND_M agrees as well as the best one can be told to
 * (see "Rep window"), and of those the smallest window wins: the latest onset with the earliest offset.
 *
 * A long rest holds thousands of candidates on each side, so the pairs are not enumerated: the offsets are
 * sorted by level, and a minimum-tree over that order answers "earliest offset whose level is within the
 * tolerance of this onset's" in O(log n).
 */
function matchLevels(onsets: readonly Boundary[], offsets: readonly Boundary[]): { onset: number; offset: number } {
  const byLevel = [...offsets].sort((p, q) => p.level - q.level);
  const levels = byLevel.map((c) => c.level);
  const n = byLevel.length;
  // tree[n + k] is the sample index of the k-th offset by level; tree[k] the smaller of its two children
  const tree: number[] = new Array<number>(2 * n).fill(Number.POSITIVE_INFINITY);
  for (let k = 0; k < n; k++) tree[n + k] = (byLevel[k] as Boundary).index;
  for (let k = n - 1; k >= 1; k--) tree[k] = Math.min(tree[2 * k] as number, tree[2 * k + 1] as number);
  /** Earliest offset among positions [from, to) of the level order. */
  const earliest = (from: number, to: number): number => {
    let min = Number.POSITIVE_INFINITY;
    for (let l = from + n, r = to + n; l < r; l >>= 1, r >>= 1) {
      if (l & 1) min = Math.min(min, tree[l++] as number);
      if (r & 1) min = Math.min(min, tree[--r] as number);
    }
    return min;
  };

  let best = Number.POSITIVE_INFINITY;
  for (const a of onsets) {
    const k = lowerBound(levels, a.level);
    if (k < n) best = Math.min(best, (levels[k] as number) - a.level);
    if (k > 0) best = Math.min(best, a.level - (levels[k - 1] as number));
  }

  const tolerance = best + DWELL_BAND_M;
  let onset = (onsets[0] as Boundary).index;
  let offset = (offsets[0] as Boundary).index;
  let span = Number.POSITIVE_INFINITY;
  for (const a of onsets) {
    // onsets come innermost first, so on equal spans the latest onset is kept
    const end = earliest(lowerBound(levels, a.level - tolerance), lowerBound(levels, a.level + tolerance));
    if (end - a.index < span) {
      span = end - a.index;
      onset = a.index;
      offset = end;
    }
  }
  return { onset, offset };
}

/**
 * Rep window. segmentReps cuts a rep minimum to minimum, which puts the whole rest before it, the pick-up, or
 * the set-down after it, into the rep: noise rectifies into work during a rest, and carrying a weight off the
 * floor is not a repetition. Each rep is therefore trimmed to its movement, on the SMOOTHED position, between
 * two pauses: one before the top (where the lift starts) and one after it (where the lowering ends).
 *
 * What a pause is. A run of DWELL_MIN_S in which the position stays within DWELL_BAND_M, that
 *  1. lies below the movement: its rest level is at least `minPhaseDisplacementM` under the rep's top, the
 *     threshold the segmenter uses to call something a phase. A pause AT the top is therefore never a
 *     boundary, however long, and neither is any stretch of the last 10 cm under the top;
 *  2. is actually at rest: the half of it away from the movement (the first half before a lift, the second
 *     half after a lowering) has a net travel of at most ONSET_TOLERANCE_M. A lift slower than about 5 cm/s
 *     stays within DWELL_BAND_M for DWELL_MIN_S anywhere along its way, and without this test the whole of a
 *     slow rep but its last centimetres was read as a rest (work -84 to -96 %).
 * Every window that qualifies is a candidate: those ending between the segmenter's start and the top for the
 * onset, those starting between the top and the segmenter's end for the offset. A window may reach outside
 * the segmenter's rep (a rest is split at its lowest sample, so part of it lies in the neighbouring rep), but
 * the onset is never before the segmenter's start nor the offset after its end.
 *
 * Which pauses. A rep starts from and returns to roughly the same height, so the onset and the offset are
 * the pair of candidates whose REST LEVELS AGREE (matchLevels). A sticking point half-way up has no pause at
 * its height on the way down, so the rests at the bottom win and the rep is whole; racking the weight at the
 * shoulders is matched by the return to the shoulders, so the press is the rep and the clean is not; a
 * pick-up from the floor followed by a pause is matched by the return to that pause's height. A rep that
 * does not come back to where it started has one height on each side and uses them.
 *  - Agreement is judged to DWELL_BAND_M. The best pair is the one with the smallest level difference; all
 *    pairs within DWELL_BAND_M of it count as agreeing equally, and of those the smallest window wins
 *    (latest onset, earliest offset). Exact minimisation does not work: the levels inside one rest differ by
 *    fractions of a millimetre once there is noise, so the exact minimum falls on an arbitrary window
 *    deep inside the rests and bills them to the rep (measured at +-2 mm with 10 s rests: start up to 8.9 s
 *    early, work +7.8 %). Two rests within the band that defines a pause are the same height as far as
 *    this rule can tell.
 *  - One candidate per rest level (onePerRestLevel). The pauses on one side of the top are grouped by
 *    level, a gap of more than SAME_REST_LEVEL_M (twice the band) separating two groups, and only the
 *    innermost pause of each group is a candidate. Two pauses at nearly the same level on the same side
 *    are the same rest seen twice; reaching for the outer one adds no movement to the rep, only rest. A
 *    hand that sways or wobbles while it rests leaves scattered pauses at levels further apart than the
 *    agreement band, and without this the matching reached for a distant pair that happened to agree
 *    (a 2 cm sway at 0.2 Hz: the rep read up to 4.2 s for 1.83 s).
 *  - Never behind the last return to the rest level. `earliest` is the last sample before the top, and
 *    `latest` the first after it, within ONSET_TOLERANCE_M of the level of the segmenter's boundary (the
 *    lowest sample on that side). The position came back to the rep's lowest level there, so nothing
 *    further out belongs to the rep: a boundary is clamped to them, and they are the boundary on a side
 *    with no pause at all. A rest that wobbles by more than DWELL_BAND_M holds no pause, and the
 *    segmenter's own boundary is its FIRST lowest sample, an arbitrary trough, often the first of the rest
 *    (a 1 cm wobble at 2.5 Hz: work +74 % after 4 s rests, +178 % after 10 s, the whole rest in the rep).
 *  - One side without a candidate (reps with no rest between them, a lowering that runs straight into the
 *    set-down): `earliest` or `latest` on that side, the innermost candidate on the other.
 *
 * Where in the pause the boundary goes. DWELL_BAND_M only detects the pause: a run stays inside the band
 * until the movement has already travelled up to 1.5 cm, and a boundary at the pause's edge cost a rep its
 * first and last centimetres (work -3.2 %, range of motion -2.6 % for 0.5 m). The boundary is the last
 * (first) sample of the pause within ONSET_TOLERANCE_M of its rest level, the median of its level half.
 *
 * Known failure modes (each measured, see the README):
 *  - Speed floor. Movement slower than ONSET_TOLERANCE_M per half of DWELL_MIN_S (2 cm/s) IS a rest to
 *    test 2, and position noise moves that to about 3 cm/s. The slow first and last centimetres of a slow
 *    rep are trimmed with the rests, more with noise; constant-speed movement at or under the floor collapses
 *    to the last `minPhaseDisplacementM` under the top. `trimmedRangeFraction` shows it.
 *  - A stop on the way up AND one at the same height on the way down is a rack to this rule: only the part
 *    above them is measured.
 *  - A stop within SAME_REST_LEVEL_M (3 cm) of the rest's height is the same rest: the rep starts or ends at
 *    the stop and reads that much short (up to 6.5 % of a 0.5 m rep).
 *  - A sway of more than about 2 cm amplitude, or a wobble with noise on top, still stretches a rep (see the
 *    README for the measured ranges), far less than before.
 *  - A stop on the way up in a rep that does not return to its start height wins if it is nearer the return
 *    height than the start is.
 *  - No pause before the set-down, or after the pick-up: nothing separates them from the rep, and the
 *    floor-to-top movement is billed to it.
 *  - A movement under the rep threshold that is NOT separated from a rep by a pause stays in that rep; one
 *    with a pause either side is attributed to neither.
 */
function trimmedWindow(y: readonly number[], rep: Rep, rateHz: number, minPhaseDisplacementM: number): { onset: number; offset: number } {
  const run = Math.max(2, Math.round(DWELL_MIN_S * rateHz) + 1); // samples in a pause: first to last spans DWELL_MIN_S
  const ceiling = (y[rep.topIndex] as number) - minPhaseDisplacementM;

  // The last time before the top, and the first time after it, that the position is at the level of the
  // segmenter's boundary (within ONSET_TOLERANCE_M). Nothing outside these two can belong to the rep: the
  // position came back to the rep's lowest level after it (before it). A pause found further out is still
  // a pause at its level, but its boundary is clamped to them, and they are the boundary on a side that has
  // no pause. (The segmenter's own boundary is the FIRST lowest sample of the rest, which in a rest that
  // wobbles is an arbitrary trough, often the first.)
  let earliest = rep.topIndex;
  while (earliest > rep.startIndex && (y[earliest] as number) > (y[rep.startIndex] as number) + ONSET_TOLERANCE_M) earliest--;
  let latest = rep.topIndex;
  while (latest < rep.endIndex && (y[latest] as number) > (y[rep.endIndex] as number) + ONSET_TOLERANCE_M) latest++;

  const onsets: Boundary[] = []; // innermost (latest) first
  for (let last = rep.topIndex; last >= rep.startIndex; last--) {
    const c = onsetCandidate(y, last, run, ceiling);
    if (c !== null) onsets.push({ index: Math.max(c.index, earliest), level: c.level });
  }
  const offsets: Boundary[] = []; // innermost (earliest) first
  for (let first = rep.topIndex; first <= rep.endIndex; first++) {
    const c = offsetCandidate(y, first, run, ceiling);
    if (c !== null) offsets.push({ index: Math.min(c.index, latest), level: c.level });
  }

  const nearOnsets = onePerRestLevel(onsets);
  const nearOffsets = onePerRestLevel(offsets);
  let onset = earliest;
  let offset = latest;
  if (nearOnsets.length > 0 && nearOffsets.length > 0) ({ onset, offset } = matchLevels(nearOnsets, nearOffsets));
  else if (nearOnsets.length > 0) onset = (nearOnsets[0] as Boundary).index;
  else if (nearOffsets.length > 0) offset = (nearOffsets[0] as Boundary).index;

  if (!(onset < rep.topIndex && rep.topIndex < offset && offset - onset >= 2)) {
    return { onset: rep.startIndex, offset: rep.endIndex };
  }
  return { onset, offset };
}

function requireNonNegativeFinite(name: string, value: number): void {
  if (!Number.isFinite(value) || value < 0) throw new RangeError(`${name} must be a finite number >= 0, got ${value}`);
}

/** `reasons` with LOW_FRAME_RATE added where assessQuality puts it: after NO_SCALE, before the rest. */
function withLowFrameRate(reasons: readonly RefusalReason[]): RefusalReason[] {
  const at = reasons[0] === "NO_SCALE" ? 1 : 0;
  return [...reasons.slice(0, at), "LOW_FRAME_RATE", ...reasons.slice(at)];
}

export function analyzeSession(frames: readonly PoseFrame[], options: SessionOptions): SessionResult {
  requireNonNegativeFinite("massKg", options.massKg);
  requireNonNegativeFinite("gEnvMs2", options.gEnvMs2);
  requireNonNegativeFinite("deviceForceN", options.deviceForceN ?? 0);
  const metersPerUnit = options.metersPerUnit;
  if (metersPerUnit !== null && (!Number.isFinite(metersPerUnit) || metersPerUnit <= 0)) {
    throw new RangeError(`metersPerUnit must be a finite number > 0, or null, got ${metersPerUnit}`);
  }

  if (options.cutoffHz !== undefined) {
    requireFinite("cutoffHz", options.cutoffHz);
    if (options.cutoffHz <= 0) throw new RangeError(`cutoffHz must be > 0, got ${options.cutoffHz}`);
  }

  const assessed = assessQuality(frames, metersPerUnit !== null, options);
  // Whether the cutoff is below the Nyquist frequency depends on the stream's frame rate, which is frame
  // content, so it is a refusal and not an exception: this stream's rate is too low for the cutoff asked for.
  const cutoffHz = options.cutoffHz ?? DEFAULT_CUTOFF_HZ;
  const quality: QualityReport =
    cutoffHz < assessed.rateHz / 2 || assessed.reasons.includes("LOW_FRAME_RATE") ? assessed : { ...assessed, reasons: withLowFrameRate(assessed.reasons) };
  if (quality.reasons.length > 0 || metersPerUnit === null) {
    return { ok: false, reasons: quality.reasons, quality };
  }

  const grid = resampleUniform(frames, options);
  // The filter needs more samples than its padding; a recording shorter than that is TOO_SHORT (at the cutoff asked for).
  if (grid.tS.length <= filterPaddingSamples(grid.rateHz, cutoffHz)) {
    const reasons: RefusalReason[] = ["TOO_SHORT"];
    return { ok: false, reasons, quality: { ...quality, reasons } };
  }
  const uniform: PoseFrame[] = grid.tS.map((tS, i) => ({ tS, wristY: grid.wristY[i] as number, visibility: 1 }));
  const metres = toMetersUp(uniform, metersPerUnit);
  const smoothed = lowPassZeroPhase(metres.map((p) => p.yM), grid.rateHz, cutoffHz);
  const samples = metres.map((p, i) => ({ tS: p.tS, yM: smoothed[i] as number }));
  // startS counts from the first frame that has a usable timestamp, so a clock that does not start at 0 changes nothing.
  const t0 = (frames.find((f) => Number.isFinite(f.tS)) as PoseFrame).tS;

  const minPhaseDisplacementM = options.minPhaseDisplacementM ?? MIN_PHASE_DISPLACEMENT_M;
  const reps: RepResult[] = segmentReps(smoothed, minPhaseDisplacementM).map((rep) => {
    const { onset, offset } = trimmedWindow(smoothed, rep, grid.rateHz, minPhaseDisplacementM);
    const window = samples.slice(onset, offset + 1);
    const work = trajectoryWork(window, options.massKg, options.gEnvMs2, { deviceForceN: options.deviceForceN ?? 0 });
    const start = samples[onset] as { tS: number; yM: number };
    const top = samples[rep.topIndex] as { tS: number; yM: number };
    const end = samples[offset] as { tS: number; yM: number };
    let liftEnd = onset;
    while (liftEnd < rep.topIndex && (smoothed[liftEnd] as number) < top.yM - ONSET_TOLERANCE_M) liftEnd++;
    const liftDurationS = (samples[liftEnd] as { tS: number }).tS - start.tS;
    const segmenterRangeM = top.yM - Math.min(smoothed[rep.startIndex] as number, smoothed[rep.endIndex] as number);
    return {
      startS: start.tS - t0,
      durationS: end.tS - start.tS,
      liftDurationS,
      filterLimited: liftDurationS < FILTER_LIMITED_LIFT_S,
      rangeOfMotionM: top.yM - start.yM,
      pathLengthM: work.pathLengthM,
      trimmedRangeFraction: (top.yM - start.yM) / segmenterRangeM,
      positiveWorkJ: work.positiveWorkJ,
      negativeWorkJ: work.negativeWorkJ,
      peakForceN: work.peakForceN,
      impulseNs: work.impulseNs,
    };
  });

  // A recording with no complete repetition (held still, or lifted and never lowered) is not a measurement of 0 J.
  if (reps.length === 0) {
    const reasons: RefusalReason[] = ["NO_REPS"];
    return { ok: false, reasons, quality: { ...quality, reasons } };
  }

  return {
    ok: true,
    reps,
    totalPositiveWorkJ: reps.reduce((sum, r) => sum + r.positiveWorkJ, 0),
    maxPeakForceN: reps.reduce((max, r) => Math.max(max, r.peakForceN), 0),
    quality,
    provenance: { loadSource: "CAMERA", confidence: confidenceOf(quality) },
  };
}
