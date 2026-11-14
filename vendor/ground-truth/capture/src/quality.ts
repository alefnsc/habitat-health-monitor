/**
 * Quality gate, gap filling and uniform resampling. A session that cannot be measured
 * honestly is refused with reason codes (a return value, never an exception).
 */

import type { PoseFrame } from "./frames";
import { requireFinite } from "./internal";

export type RefusalReason = "NO_SCALE" | "LOW_FRAME_RATE" | "LANDMARK_LOST" | "GAP_TOO_LONG" | "TOO_SHORT" | "NO_REPS";

/**
 * Judgement call: below this a 1 s lift has too few samples. Set under every nominal
 * camera rate (23.976, 24, 25, 29.97, 30), which a median of measured timestamps can land
 * a hair either side of, so no real camera is refused or graded by rounding.
 */
export const MIN_RATE_HZ = 20;
/** Judgement call: a frame whose landmark visibility is below this is not trusted. */
export const VISIBILITY_THRESHOLD = 0.5;
/** Judgement call. */
export const MAX_LOW_VISIBILITY_FRACTION = 0.1;
/** Judgement call: a quarter of a typical 1 s lift. */
export const MAX_GAP_S = 0.25;
/** Judgement call: one rep takes about 2 s; a recording under 1 s cannot contain one. */
export const MIN_DURATION_S = 1.0;

/** The two limits a caller may move; the exported constants are the defaults. */
export interface QualityOptions {
  /** A frame whose landmark visibility is below this is not trusted, within [0, 1]. Default VISIBILITY_THRESHOLD. */
  visibilityThreshold?: number;
  /** The longest run of missing or low-visibility time (seconds) that is bridged, > 0. Default MAX_GAP_S. */
  maxGapS?: number;
}

interface Limits {
  visibilityThreshold: number;
  maxGapS: number;
}

function limitsOf(options: QualityOptions | undefined): Limits {
  const visibilityThreshold = options?.visibilityThreshold ?? VISIBILITY_THRESHOLD;
  const maxGapS = options?.maxGapS ?? MAX_GAP_S;
  requireFinite("visibilityThreshold", visibilityThreshold);
  if (visibilityThreshold < 0 || visibilityThreshold > 1) throw new RangeError(`visibilityThreshold must be within [0, 1], got ${visibilityThreshold}`);
  requireFinite("maxGapS", maxGapS);
  if (maxGapS <= 0) throw new RangeError(`maxGapS must be > 0, got ${maxGapS}`);
  return { visibilityThreshold, maxGapS };
}

export interface QualityReport {
  rateHz: number; // median frame rate
  lowVisibilityFraction: number;
  longestGapS: number; // longest run of missing or low-visibility time
  durationS: number;
  /** Frames discarded before assessing because their timestamp was not finite or not greater than the last kept one (a video frame processed twice, or delivered out of order). */
  droppedFrames: number;
  reasons: RefusalReason[]; // empty when acceptable
}

/**
 * A wristY this large is not an image coordinate (normalised ones are within a few frame
 * widths of 0..1): the frame is garbage and counts as a lost landmark. It also keeps
 * interpolation and the metre conversion from overflowing.
 */
const MAX_ABS_WRIST_Y = 1e6;

/**
 * Judgement call: the uniform grid may hold at most this many samples per frame delivered.
 * A real stream has about one (a hole of a quarter of a second at most still leaves 0.5);
 * timestamps whose median spacing is far tighter than their overall spacing would otherwise
 * ask resampleUniform for millions of samples.
 */
const MAX_GRID_SAMPLES_PER_FRAME = 4;

/**
 * The frames in strictly increasing time, and how many were dropped to get there. A frame
 * is dropped when its timestamp is not finite or not greater than the last frame kept (a
 * duplicate, or one delivered out of order). Nothing about frame content throws.
 */
function inTimeOrder(frames: readonly PoseFrame[]): { kept: PoseFrame[]; dropped: number } {
  const kept: PoseFrame[] = [];
  let lastT = Number.NEGATIVE_INFINITY;
  for (const f of frames) {
    if (!Number.isFinite(f.tS) || f.tS <= lastT) continue;
    kept.push(f);
    lastT = f.tS;
  }
  return { kept, dropped: frames.length - kept.length };
}

/**
 * Median frame rate over ALL frames (the camera's rate, not the usable one), so a hole
 * in the timestamps or a run of flagged frames does not move it. 0 when under 2 frames.
 */
function medianRateHz(frames: readonly PoseFrame[]): number {
  if (frames.length < 2) return 0;
  const dts = frames.slice(1).map((f, i) => f.tS - (frames[i] as PoseFrame).tS).sort((a, b) => a - b);
  const mid = dts.length >> 1;
  const medianDt = dts.length % 2 === 1 ? (dts[mid] as number) : ((dts[mid - 1] as number) + (dts[mid] as number)) / 2;
  return 1 / medianDt;
}

/** A frame the pipeline may use: a finite wristY and a visibility at or above the threshold (NaN fails the comparison). */
const isVisible = (f: PoseFrame, visibilityThreshold: number): boolean =>
  Number.isFinite(f.wristY) && Math.abs(f.wristY) < MAX_ABS_WRIST_Y && f.visibility >= visibilityThreshold;

/**
 * Gaps are measured between usable frames: the time from one visible frame to the next
 * visible one, so a run of k lost frames at rate r is (k + 1) / r, and a hole in the
 * timestamps is its own width. Time lost at the start or end of the recording (before
 * the first or after the last visible frame) counts too. With no visible frame the
 * whole recording is one gap.
 */
function longestGapS(frames: readonly PoseFrame[], visibilityThreshold: number): number {
  if (frames.length === 0) return 0;
  const first = (frames[0] as PoseFrame).tS;
  const last = (frames[frames.length - 1] as PoseFrame).tS;
  let longest = 0;
  let previousVisibleT = first;
  let sawVisible = false;
  for (const f of frames) {
    if (!isVisible(f, visibilityThreshold)) continue;
    if (sawVisible) longest = Math.max(longest, f.tS - previousVisibleT);
    else longest = Math.max(longest, f.tS - first); // lost time at the start
    previousVisibleT = f.tS;
    sawVisible = true;
  }
  if (!sawVisible) return last - first;
  return Math.max(longest, last - previousVisibleT); // lost time at the end
}

export function assessQuality(frames: readonly PoseFrame[], hasScale: boolean, options?: QualityOptions): QualityReport {
  const { visibilityThreshold, maxGapS } = limitsOf(options);
  const { kept, dropped } = inTimeOrder(frames);
  const rateHz = medianRateHz(kept);
  const lowVisibilityFraction = kept.length === 0 ? 0 : kept.filter((f) => !isVisible(f, visibilityThreshold)).length / kept.length;
  const droppedFraction = frames.length === 0 ? 0 : dropped / frames.length;
  const gapS = longestGapS(kept, visibilityThreshold);
  const durationS = kept.length < 2 ? 0 : (kept[kept.length - 1] as PoseFrame).tS - (kept[0] as PoseFrame).tS;

  const reasons: RefusalReason[] = [];
  if (!hasScale) reasons.push("NO_SCALE");
  // The effective rate is what was delivered: a median spacing far tighter than the stream's overall spacing is no frame rate.
  const gridTooDense = rateHz * durationS + 1 > MAX_GRID_SAMPLES_PER_FRAME * kept.length;
  if (rateHz < MIN_RATE_HZ || gridTooDense) reasons.push("LOW_FRAME_RATE");
  // Frames dropped for their timestamps are lost frames too: too many of them is a stream that cannot be trusted.
  if (lowVisibilityFraction > MAX_LOW_VISIBILITY_FRACTION || droppedFraction > MAX_LOW_VISIBILITY_FRACTION) reasons.push("LANDMARK_LOST");
  if (gapS > maxGapS) reasons.push("GAP_TOO_LONG");
  if (durationS < MIN_DURATION_S) reasons.push("TOO_SHORT");

  return { rateHz, lowVisibilityFraction, longestGapS: gapS, durationS, droppedFrames: dropped, reasons };
}

/**
 * Drops frames that are not in time order and low-visibility frames (their wristY is never read), then linearly interpolates
 * onto a uniform grid at the median frame rate. The grid runs from the first to the last
 * visible frame: nothing is extrapolated. tS is on the frames' own clock. Only
 * `visibilityThreshold` of the options matters here (the gap limit is the gate's).
 */
export function resampleUniform(
  frames: readonly PoseFrame[],
  options?: QualityOptions,
): { rateHz: number; tS: number[]; wristY: number[] } {
  const { visibilityThreshold } = limitsOf(options);
  const ordered = inTimeOrder(frames).kept;
  const rateHz = medianRateHz(ordered);
  const kept = ordered.filter((f) => isVisible(f, visibilityThreshold));
  if (kept.length < 2) {
    throw new RangeError(`frames must contain at least 2 usable frames (finite time and wristY, visibility >= ${visibilityThreshold}), got ${kept.length}`);
  }

  const t0 = (kept[0] as PoseFrame).tS;
  const tEnd = (kept[kept.length - 1] as PoseFrame).tS;
  const count = Math.floor((tEnd - t0) * rateHz + 1e-9) + 1;
  const tS: number[] = new Array<number>(count);
  const wristY: number[] = new Array<number>(count);
  let j = 0; // kept[j] <= t < kept[j + 1]
  for (let k = 0; k < count; k++) {
    const t = t0 + k / rateHz;
    while (j < kept.length - 2 && (kept[j + 1] as PoseFrame).tS <= t) j++;
    const a = kept[j] as PoseFrame;
    const b = kept[j + 1] as PoseFrame;
    const w = (t - a.tS) / (b.tS - a.tS);
    tS[k] = t;
    wristY[k] = a.wristY + w * (b.wristY - a.wristY);
  }
  return { rateHz, tS, wristY };
}
