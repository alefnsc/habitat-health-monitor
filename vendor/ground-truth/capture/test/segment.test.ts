import { describe, expect, it } from "vitest";
import { MIN_PHASE_DISPLACEMENT_M, segmentReps } from "../src/index";
import { lcg, minJerk } from "./helpers";

const FS = 60;

type Step = { to: number; s: number } | { hold: number };

/** A clean trace at 60 Hz: from `start`, a sequence of minimum-jerk moves to a level, or holds. */
function trace(steps: readonly Step[], start = 0): number[] {
  const y = [start];
  let level = start;
  for (const step of steps) {
    if ("hold" in step) {
      for (let i = 1; i <= Math.round(step.hold * FS); i++) y.push(level);
    } else {
      const n = Math.round(step.s * FS);
      for (let i = 1; i <= n; i++) y.push(level + (step.to - level) * minJerk(i / n));
      level = step.to;
    }
  }
  return y;
}

const rep = (h = 0.5): Step[] => [{ to: h, s: 1 }, { to: 0, s: 1 }];
const rest: Step = { hold: 0.5 };

describe("segmentReps", () => {
  it("the default minimum phase displacement is 0.10 m", () => {
    expect(MIN_PHASE_DISPLACEMENT_M).toBe(0.1);
  });

  it("3 reps of 0.5 m with 0.5 s rests: 3 reps, each lifting 0.5 m, in order and not overlapping", () => {
    const y = trace([rest, ...rep(), rest, ...rep(), rest, ...rep(), rest]);
    const reps = segmentReps(y);
    expect(reps).toHaveLength(3);
    reps.forEach((r, k) => {
      expect(r.startIndex).toBeLessThan(r.topIndex);
      expect(r.topIndex).toBeLessThan(r.endIndex);
      expect(Math.abs((y[r.topIndex] as number) - (y[r.startIndex] as number) - 0.5) / 0.5).toBeLessThan(0.02);
      expect(Math.abs((y[r.topIndex] as number) - (y[r.endIndex] as number) - 0.5) / 0.5).toBeLessThan(0.02);
      if (k > 0) expect(r.startIndex).toBeGreaterThanOrEqual((reps[k - 1] as { endIndex: number }).endIndex);
    });
    // each top is where the lift ends: 0.5 s rest + 1 s up, then every 2.5 s
    reps.forEach((r, k) => expect(Math.abs(r.topIndex - (1.5 + 2.5 * k) * FS)).toBeLessThanOrEqual(1));
  });

  it("a stationary signal with ±3 mm ripple: 0 reps", () => {
    const noise = lcg(5);
    const y = Array.from({ length: 360 }, () => 0.003 * noise());
    expect(segmentReps(y)).toEqual([]);
  });

  it("a deterministic ±3 mm sine ripple that reverses every few samples: 0 reps", () => {
    const y = Array.from({ length: 360 }, (_, i) => 0.003 * Math.sin(i * 1.3));
    expect(segmentReps(y)).toEqual([]);
  });

  it("one lift, no lowering: 0 reps", () => {
    expect(segmentReps(trace([rest, { to: 0.5, s: 1 }, rest]))).toEqual([]);
  });

  it("one lowering and nothing else: 0 reps", () => {
    expect(segmentReps(trace([rest, { to: -0.5, s: 1 }, rest]))).toEqual([]);
  });

  it("2 reps with no rest between them: 2 reps, the first ends where the second starts (±2 samples)", () => {
    const y = trace([...rep(), ...rep()]);
    const reps = segmentReps(y);
    expect(reps).toHaveLength(2);
    expect(Math.abs((reps[0] as { endIndex: number }).endIndex - (reps[1] as { startIndex: number }).startIndex)).toBeLessThanOrEqual(2);
    expect((reps[0] as { startIndex: number }).startIndex).toBe(0);
    expect((reps[1] as { endIndex: number }).endIndex).toBe(y.length - 1);
  });

  it("a 0.5 m rep with a 0.05 m dip half-way up: 1 rep (the dip is under the threshold)", () => {
    const y = trace([rest, { to: 0.25, s: 0.5 }, { to: 0.2, s: 0.2 }, { to: 0.5, s: 0.5 }, { to: 0, s: 1 }, rest]);
    // guard the test itself: the dip really is there, as a reversal in the trace
    const dipStart = Math.round((0.5 + 0.5) * FS);
    const dipEnd = dipStart + Math.round(0.2 * FS);
    expect((y[dipEnd] as number) - (y[dipStart] as number)).toBeCloseTo(-0.05, 9);
    const reps = segmentReps(y);
    expect(reps).toHaveLength(1);
    expect((y[(reps[0] as { topIndex: number }).topIndex] as number)).toBeCloseTo(0.5, 9);
  });

  it("a dip of 0.15 m half-way up is a real reversal at the default threshold, and jitter at a threshold of 0.2 m", () => {
    const y = trace([rest, { to: 0.3, s: 0.6 }, { to: 0.15, s: 0.4 }, { to: 0.5, s: 0.6 }, { to: 0, s: 1 }, rest]);
    // up 0.3, down 0.15, up 0.35, down 0.5: two up-down pairs, so two reps
    expect(segmentReps(y)).toHaveLength(2);
    expect(segmentReps(y, 0.2)).toHaveLength(1);
  });

  it("reps of 0.08 m: 0 reps by default, 3 with minPhaseDisplacementM = 0.05", () => {
    const y = trace([rest, ...rep(0.08), rest, ...rep(0.08), rest, ...rep(0.08), rest]);
    expect(segmentReps(y)).toEqual([]);
    expect(segmentReps(y, 0.05)).toHaveLength(3);
  });

  it("starts mid-lowering: the partial movement is ignored and the later full reps are counted", () => {
    const y = trace([{ to: 0, s: 0.6 }, rest, ...rep(), rest, ...rep(), rest], 0.3);
    const reps = segmentReps(y);
    expect(reps).toHaveLength(2);
    // the first rep starts after the partial lowering, at the bottom
    expect((reps[0] as { startIndex: number }).startIndex).toBeGreaterThan(Math.round(0.5 * FS));
    reps.forEach((r) => expect((y[r.topIndex] as number) - (y[r.startIndex] as number)).toBeCloseTo(0.5, 6));
  });

  it("ripple on top of real reps does not change the count or the extrema by more than the ripple", () => {
    const noise = lcg(9);
    const clean = trace([rest, ...rep(), rest, ...rep(), rest, ...rep(), rest]);
    const y = clean.map((v) => v + 0.003 * noise());
    const reps = segmentReps(y);
    expect(reps).toHaveLength(3);
    reps.forEach((r) => expect(Math.abs((y[r.topIndex] as number) - (y[r.startIndex] as number) - 0.5)).toBeLessThan(0.01));
  });

  it("works whatever the offset or scale of the trace", () => {
    const base = trace([rest, ...rep(), rest, ...rep(), rest]);
    expect(segmentReps(base.map((v) => v - 12.3))).toEqual(segmentReps(base));
  });

  it("a trace that ends before the last lowering is finished still ends the rep once the lowering exceeds the threshold", () => {
    const y = trace([rest, { to: 0.5, s: 1 }, { to: 0, s: 1 }]).slice(0, -30); // stops half-way down
    const reps = segmentReps(y);
    expect(reps).toHaveLength(1);
    expect((reps[0] as { endIndex: number }).endIndex).toBe(y.length - 1);
  });

  it("empty and very short traces have no reps", () => {
    expect(segmentReps([])).toEqual([]);
    expect(segmentReps([0.1])).toEqual([]);
    expect(segmentReps([0, 1])).toEqual([]);
  });

  it("rejects a non-positive threshold and non-finite positions", () => {
    expect(() => segmentReps([0, 1, 0], 0)).toThrow(RangeError);
    expect(() => segmentReps([0, 1, 0], -0.1)).toThrow(/minPhaseDisplacementM/);
    expect(() => segmentReps([0, 1, 0], Number.NaN)).toThrow(/minPhaseDisplacementM/);
    expect(() => segmentReps([0, Number.NaN, 0])).toThrow(/yM\[1\]/);
  });
});
