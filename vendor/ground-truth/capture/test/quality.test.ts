import { describe, expect, it } from "vitest";
import {
  MAX_GAP_S,
  MAX_LOW_VISIBILITY_FRACTION,
  MIN_DURATION_S,
  MIN_RATE_HZ,
  VISIBILITY_THRESHOLD,
  assessQuality,
  resampleUniform,
  type PoseFrame,
} from "../src/index";
import { lcg } from "./helpers";

/** A clean recording: `seconds` at `rateHz`, a slow wrist oscillation, visibility 1. */
function clean(rateHz: number, seconds: number): PoseFrame[] {
  const n = Math.round(seconds * rateHz) + 1;
  return Array.from({ length: n }, (_, i) => {
    const tS = i / rateHz;
    return { tS, wristY: 0.5 + 0.1 * Math.sin(2 * Math.PI * 0.5 * tS), visibility: 1 };
  });
}

/** Lower the visibility of every frame whose index is in `indices`, and put garbage in its wristY. */
function withLowVisibility(frames: PoseFrame[], indices: Iterable<number>, wristY = 999): PoseFrame[] {
  const set = new Set(indices);
  return frames.map((f, i) => (set.has(i) ? { ...f, visibility: 0.2, wristY } : f));
}

const every = (frames: readonly PoseFrame[], k: number, offset = 3): number[] =>
  frames.map((_, i) => i).filter((i) => i % k === offset);

describe("thresholds", () => {
  it("are the plan's values, except the frame-rate floor, which sits below the nominal camera rates (20 Hz)", () => {
    expect(MIN_RATE_HZ).toBe(20);
    expect(VISIBILITY_THRESHOLD).toBe(0.5);
    expect(MAX_LOW_VISIBILITY_FRACTION).toBe(0.1);
    expect(MAX_GAP_S).toBe(0.25);
    expect(MIN_DURATION_S).toBe(1.0);
  });
});

describe("assessQuality", () => {
  it("clean 60 Hz, 6 s, with scale: no reasons and the measured numbers", () => {
    const q = assessQuality(clean(60, 6), true);
    expect(q.reasons).toEqual([]);
    expect(q.rateHz).toBeCloseTo(60, 6);
    expect(q.durationS).toBeCloseTo(6, 9);
    expect(q.lowVisibilityFraction).toBe(0);
    expect(q.longestGapS).toBeCloseTo(1 / 60, 9);
    expect(q.droppedFrames).toBe(0);
  });

  it("the same without a scale: only NO_SCALE", () => {
    expect(assessQuality(clean(60, 6), false).reasons).toEqual(["NO_SCALE"]);
  });

  it("15 Hz includes LOW_FRAME_RATE; the nominal 23.976, 24, 25, 29.97 and 30 fps do not", () => {
    expect(assessQuality(clean(15, 6), true).reasons).toContain("LOW_FRAME_RATE");
    expect(assessQuality(clean(15, 6), true).reasons).toEqual(["LOW_FRAME_RATE"]);
    for (const rateHz of [20, 23.976, 24, 25, 29.97, 30]) expect(assessQuality(clean(rateHz, 6), true).reasons).toEqual([]);
  });

  it("15 % of frames at visibility 0.2, scattered, includes LANDMARK_LOST (and nothing about gaps)", () => {
    const frames = clean(60, 6);
    const bad = frames.map((_, i) => i).filter((i) => (i * 20) % 133 < 20); // ~15 %, no long runs
    const q = assessQuality(withLowVisibility(frames, bad), true);
    expect(q.lowVisibilityFraction).toBeGreaterThan(0.12);
    expect(q.lowVisibilityFraction).toBeLessThan(0.18);
    expect(q.longestGapS).toBeLessThan(MAX_GAP_S);
    expect(q.reasons).toEqual(["LANDMARK_LOST"]);
  });

  it("5 % low-visibility, scattered: no reasons", () => {
    const frames = clean(60, 6);
    const q = assessQuality(withLowVisibility(frames, every(frames, 20)), true);
    expect(q.lowVisibilityFraction).toBeCloseTo(0.05, 2);
    expect(q.reasons).toEqual([]);
  });

  it("a visibility exactly at the threshold counts as visible", () => {
    const frames = clean(60, 6).map((f, i) => (i % 2 === 0 ? { ...f, visibility: VISIBILITY_THRESHOLD } : f));
    expect(assessQuality(frames, true).lowVisibilityFraction).toBe(0);
  });

  it("0.4 s of consecutive low-visibility frames includes GAP_TOO_LONG", () => {
    const frames = clean(60, 6);
    const run = Array.from({ length: 24 }, (_, i) => 100 + i); // 24 frames = 0.4 s
    const q = assessQuality(withLowVisibility(frames, run), true);
    expect(q.longestGapS).toBeCloseTo(25 / 60, 9); // distance between the good frames either side
    expect(q.reasons).toEqual(["GAP_TOO_LONG"]);
  });

  it("a gap just under the limit is accepted: 14 lost frames at 60 Hz leave 15/60 = 0.25 s, which is not over", () => {
    const frames = clean(60, 6);
    const run = Array.from({ length: 14 }, (_, i) => 100 + i);
    const q = assessQuality(withLowVisibility(frames, run), true);
    expect(q.longestGapS).toBeCloseTo(0.25, 9);
    expect(q.reasons).toEqual([]);
  });

  it("a 0.4 s hole in the timestamps (frames missing, none flagged) includes GAP_TOO_LONG, and the median rate is unharmed", () => {
    const frames = clean(60, 6);
    const holed = [...frames.slice(0, 100), ...frames.slice(124)]; // drop 24 frames
    const q = assessQuality(holed, true);
    expect(q.rateHz).toBeCloseTo(60, 6);
    expect(q.longestGapS).toBeCloseTo(25 / 60, 9);
    expect(q.reasons).toEqual(["GAP_TOO_LONG"]);
  });

  it("a lost landmark at the very start or end counts as a gap", () => {
    const frames = clean(60, 6);
    const lead = Array.from({ length: 30 }, (_, i) => i); // 0.5 s at the start
    expect(assessQuality(withLowVisibility(frames, lead), true).reasons).toContain("GAP_TOO_LONG");
    const tail = Array.from({ length: 30 }, (_, i) => frames.length - 1 - i);
    expect(assessQuality(withLowVisibility(frames, tail), true).reasons).toContain("GAP_TOO_LONG");
  });

  it("a 0.5 s recording includes TOO_SHORT", () => {
    const q = assessQuality(clean(60, 0.5), true);
    expect(q.durationS).toBeCloseTo(0.5, 9);
    expect(q.reasons).toEqual(["TOO_SHORT"]);
  });

  it("several problems at once: every applicable reason, in the order of the union type", () => {
    // 15 Hz, 0.5 s, no scale, and 4 of 9 frames lost in one run: all five.
    const frames = withLowVisibility(clean(15, 0.5), [2, 3, 4, 5]);
    const q = assessQuality(frames, false);
    expect(q.reasons).toEqual(["NO_SCALE", "LOW_FRAME_RATE", "LANDMARK_LOST", "GAP_TOO_LONG", "TOO_SHORT"]);
    // a subset: no scale, slow, and one lost run, but long enough and few enough lost frames
    const q2 = assessQuality(withLowVisibility(clean(15, 6), Array.from({ length: 6 }, (_, i) => 20 + i)), false);
    expect(q2.reasons).toEqual(["NO_SCALE", "LOW_FRAME_RATE", "GAP_TOO_LONG"]);
  });

  it("every frame lost: the whole recording is one gap", () => {
    const frames = clean(60, 6);
    const q = assessQuality(withLowVisibility(frames, frames.map((_, i) => i)), true);
    expect(q.lowVisibilityFraction).toBe(1);
    expect(q.longestGapS).toBeCloseTo(6, 9);
    expect(q.reasons).toEqual(["LANDMARK_LOST", "GAP_TOO_LONG"]);
  });

  it("no frames or one frame: refused for rate and length, without NaN", () => {
    for (const frames of [[], clean(60, 0).slice(0, 1)]) {
      const q = assessQuality(frames, true);
      expect(q.rateHz).toBe(0);
      expect(q.durationS).toBe(0);
      expect(q.lowVisibilityFraction).toBe(0);
      expect(q.reasons).toEqual(["LOW_FRAME_RATE", "TOO_SHORT"]);
    }
  });

  it("a frame processed twice (same timestamp) is dropped and counted, not thrown on", () => {
    const frames = clean(60, 6);
    const doubled = frames.flatMap((f, i) => (i % 50 === 7 ? [f, { ...f }] : [f])); // 2 % of the stream repeated
    const q = assessQuality(doubled, true);
    expect(q.droppedFrames).toBe(frames.filter((_, i) => i % 50 === 7).length);
    expect(q.rateHz).toBeCloseTo(60, 6);
    expect(q.reasons).toEqual([]);
  });

  it("an out-of-order frame (a timestamp before the previous one) is dropped and counted", () => {
    const f = clean(60, 6);
    const q = assessQuality([...f.slice(0, 100), f[50]!, ...f.slice(100)], true);
    expect(q.droppedFrames).toBe(1);
    expect(q.rateHz).toBeCloseTo(60, 6);
    expect(q.reasons).toEqual([]);
  });

  it("more than MAX_LOW_VISIBILITY_FRACTION of the stream dropped for its timestamps is LANDMARK_LOST", () => {
    const f = clean(60, 6);
    const doubled = f.flatMap((x, i) => (i % 6 === 0 ? [x, { ...x }] : [x])); // 1 in 6 repeated: 16.7 %
    const q = assessQuality(doubled, true);
    expect(q.droppedFrames).toBe(f.filter((_, i) => i % 6 === 0).length);
    expect(q.droppedFrames / doubled.length).toBeGreaterThan(MAX_LOW_VISIBILITY_FRACTION);
    expect(q.reasons).toEqual(["LANDMARK_LOST"]);
  });

  it("a non-finite timestamp is dropped; a non-finite or out-of-range visibility or a non-finite wristY is a lost landmark", () => {
    const f = clean(60, 6);
    const q = assessQuality([f[0]!, { ...f[1]!, tS: Number.NaN }, ...f.slice(2)], true);
    expect(q.droppedFrames).toBe(1);
    expect(q.reasons).toEqual([]);
    const lost = assessQuality(
      f.map((x, i) => (i === 10 ? { ...x, visibility: Number.NaN } : i === 20 ? { ...x, wristY: Number.NaN } : i === 30 ? { ...x, visibility: -1 } : x)),
      true,
    );
    expect(lost.lowVisibilityFraction).toBeCloseTo(3 / f.length, 9);
    expect(lost.droppedFrames).toBe(0);
  });

  it("timestamps in milliseconds are refused, not thrown on: the frame rate reads as 0.06 Hz", () => {
    const ms = clean(60, 6).map((x) => ({ ...x, tS: x.tS * 1000 }));
    const q = assessQuality(ms, true);
    expect(q.reasons).toContain("LOW_FRAME_RATE");
  });
});

describe("assessQuality: overridable limits", () => {
  it("visibilityThreshold moves what counts as lost, and maxGapS what counts as a long gap", () => {
    const murky = clean(60, 6).map((f) => ({ ...f, visibility: 0.45 }));
    expect(assessQuality(murky, true).reasons).toContain("LANDMARK_LOST");
    expect(assessQuality(murky, true, { visibilityThreshold: 0.4 }).reasons).toEqual([]);
    const run = Array.from({ length: 24 }, (_, i) => 100 + i); // a 0.42 s gap
    const gappy = withLowVisibility(clean(60, 6), run);
    expect(assessQuality(gappy, true).reasons).toEqual(["GAP_TOO_LONG"]);
    expect(assessQuality(gappy, true, { maxGapS: 0.5 }).reasons).toEqual([]);
    expect(assessQuality(gappy, true, { maxGapS: 0.4 }).reasons).toEqual(["GAP_TOO_LONG"]);
    expect(() => assessQuality(gappy, true, { maxGapS: -1 })).toThrow(/maxGapS/);
    expect(() => assessQuality(gappy, true, { visibilityThreshold: 2 })).toThrow(/visibilityThreshold/);
  });

  it("resampleUniform honours the same visibilityThreshold", () => {
    const murky = clean(60, 3).map((f) => ({ ...f, visibility: 0.45 }));
    expect(() => resampleUniform(murky)).toThrow(RangeError);
    expect(resampleUniform(murky, { visibilityThreshold: 0.4 }).tS.length).toBeGreaterThan(170);
  });
});

describe("resampleUniform", () => {
  it("jittered timestamps of a known line come out on the line, uniformly spaced", () => {
    const jitter = lcg(11);
    const line = (t: number) => 0.2 + 0.05 * t;
    const frames: PoseFrame[] = Array.from({ length: 301 }, (_, i) => {
      const tS = i / 60 + (i === 0 || i === 300 ? 0 : 0.004 * jitter());
      return { tS, wristY: line(tS), visibility: 1 };
    });
    const out = resampleUniform(frames);
    expect(out.rateHz).toBeGreaterThan(55);
    expect(out.rateHz).toBeLessThan(65);
    expect(out.tS.length).toBe(out.wristY.length);
    expect(out.tS.length).toBeGreaterThan(290);
    expect(out.tS[0]).toBe(frames[0]!.tS);
    expect(out.tS[out.tS.length - 1]!).toBeLessThanOrEqual(frames[300]!.tS + 1e-9);
    for (let k = 0; k < out.tS.length; k++) {
      expect(Math.abs(out.wristY[k]! - line(out.tS[k]!))).toBeLessThan(1e-9);
      if (k > 0) expect(Math.abs(out.tS[k]! - out.tS[k - 1]! - 1 / out.rateHz)).toBeLessThan(1e-9);
    }
  });

  it("low-visibility frames carrying garbage wristY never reach the output, and the gap is bridged linearly", () => {
    const line = (t: number) => 0.3 + 0.1 * t;
    const base: PoseFrame[] = Array.from({ length: 361 }, (_, i) => ({ tS: i / 60, wristY: line(i / 60), visibility: 1 }));
    const frames = withLowVisibility(base, every(base, 7), 1e6);
    const out = resampleUniform(frames);
    expect(out.tS.length).toBeGreaterThan(350);
    for (let k = 0; k < out.tS.length; k++) {
      expect(Math.abs(out.wristY[k]! - line(out.tS[k]!))).toBeLessThan(1e-9);
    }
    expect(Math.max(...out.wristY)).toBeLessThan(1);
  });

  it("NaN garbage in a low-visibility frame is tolerated too", () => {
    const base = clean(60, 3);
    const frames = withLowVisibility(base, every(base, 10), Number.NaN);
    const out = resampleUniform(frames);
    expect(out.wristY.every(Number.isFinite)).toBe(true);
  });

  it("a hole in the timestamps is bridged by linear interpolation", () => {
    const line = (t: number) => 0.5 - 0.02 * t;
    const base: PoseFrame[] = Array.from({ length: 181 }, (_, i) => ({ tS: i / 60, wristY: line(i / 60), visibility: 1 }));
    const out = resampleUniform([...base.slice(0, 60), ...base.slice(84)]);
    expect(out.tS).toHaveLength(181);
    out.tS.forEach((t, k) => expect(out.wristY[k]!).toBeCloseTo(line(t), 9));
  });

  it("does not extrapolate: the grid lies within the first and last visible frames", () => {
    const frames = withLowVisibility(clean(60, 3), [0, 1, 2, 178, 179, 180]);
    const out = resampleUniform(frames);
    expect(out.tS[0]).toBeCloseTo(3 / 60, 12);
    expect(out.tS[out.tS.length - 1]!).toBeCloseTo(177 / 60, 9);
  });

  it("a stream with frames repeated or out of order is resampled from the frames that are in time order", () => {
    const line = (t: number) => 0.3 + 0.1 * t;
    const base: PoseFrame[] = Array.from({ length: 181 }, (_, i) => ({ tS: i / 60, wristY: line(i / 60), visibility: 1 }));
    const messy = [...base.slice(0, 50), base[10]!, base[50]!, ...base.slice(50)];
    const out = resampleUniform(messy);
    expect(out.tS).toHaveLength(181);
    out.tS.forEach((t, k) => expect(out.wristY[k]!).toBeCloseTo(line(t), 9));
  });

  it("needs at least two visible frames", () => {
    expect(() => resampleUniform([])).toThrow(RangeError);
    const one = withLowVisibility(clean(60, 1), Array.from({ length: 60 }, (_, i) => i));
    expect(() => resampleUniform(one)).toThrow(/frames/);
  });
});
