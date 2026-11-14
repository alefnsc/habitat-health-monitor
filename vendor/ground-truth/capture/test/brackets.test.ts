import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { DWELL_BAND_M, DWELL_MIN_S, FILTER_LIMITED_LIFT_S, SAME_REST_LEVEL_M, analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { legSession, repLegs, syntheticSession, type Leg } from "./helpers";

// Brackets. Each judgement-call constant of the rep window is held between two scenarios, one that
// breaks if it is halved and one that breaks if it is doubled, so a change to any of them is a decision
// and not an accident. Below them: the option that must reach the resampler, and pins of the failure
// modes the README states. Numbers in comments are measured on synthetic signals at 60 Hz.

const SCALE = 2.5;
const MASS_KG = 10;
const EARTH = G_ENV_MS2.EARTH;
const MG = MASS_KG * EARTH;

function analyze(frames: readonly PoseFrame[], over: Partial<Parameters<typeof analyzeSession>[1]> = {}): Extract<SessionResult, { ok: true }> {
  const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE, ...over });
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

const relErr = (actual: number, expected: number): number => Math.abs(actual - expected) / Math.abs(expected);
const seeds = (n: number): number[] => Array.from({ length: n }, (_, i) => i + 1);

describe("DWELL_MIN_S = 0.3 s is bracketed", () => {
  it("is 0.3", () => {
    expect(DWELL_MIN_S).toBe(0.3);
  });

  it("a 0.35 s pause at the shoulders is a pause (fails if the constant is doubled): rack, two presses, each 0.5 m", () => {
    // Doubled, a 0.35 s pause is no pause and the first press is measured from the floor (0.9 m).
    const legs: Leg[] = [[1, 0], [1, 0.4], [0.35, 0.4], [1, 0.9], [1, 0.4], [0.35, 0.4], [1, 0.9], [1, 0.4], [0.35, 0.4], [1, 0], [1, 0]];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs, noiseM, seed }));
        expect(r.reps).toHaveLength(2);
        for (const rep of r.reps) {
          expect(relErr(rep.rangeOfMotionM, 0.5)).toBeLessThan(0.013); // measured 0.63 % worst
          expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.015); // measured 0.72 %
          expect(relErr(-rep.negativeWorkJ, MG * 0.5)).toBeLessThan(0.015); // measured 0.68 %
        }
      }
    }
  });

  it("a 0.5 m lift over 8 s is not a string of pauses (fails if the constant is halved): work within 4.5 %", () => {
    // Halved, the still half of a pause is 0.07 s and the speed floor doubles to 4 cm/s. Measured -2.2 %.
    const r = analyze(legSession({ legs: repLegs(2, 0.5, 8, 8, 3) }));
    expect(r.reps).toHaveLength(2);
    for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.045);
  });
});

describe("DWELL_BAND_M = 1.5 cm is bracketed", () => {
  // Twice the band (SAME_REST_LEVEL_M, 3 cm) is how close two pauses on one side of the top must be to
  // count as the same rest, of which only the one nearer the top can bound the rep. A stop on the way
  // down, a little above the rest the rep started from, is therefore the end of the rep if it is within
  // 3 cm of the rest (the rep reads that much short) and not if it is further (the rep runs on to the rest).
  const stopAbove = (gapM: number): Leg[] => [[3, 0], [1, 0.5], [1, gapM], [0.6, gapM], [0.4, 0], [3, 0]];
  const NOISE: readonly (readonly [number, readonly number[]])[] = [[0, [1]], [0.002, seeds(10)]];

  it("is 0.015, and two pauses within 0.03 are the same rest", () => {
    expect(DWELL_BAND_M).toBe(0.015);
    expect(SAME_REST_LEVEL_M).toBe(0.03);
  });

  it("a 0.6 s stop 5 cm above the start is NOT the end of the rep (fails if the constant is doubled): the rep runs on to the rest", () => {
    // measured: durationS 2.85 to 2.88, W- -0.3 to +0.3 %
    for (const [noiseM, seedList] of NOISE) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs: stopAbove(0.05), noiseM, seed })).reps[0]!;
        expect(Math.abs(rep.durationS - 2.867)).toBeLessThan(0.035);
        expect(relErr(-rep.negativeWorkJ, MG * 0.5)).toBeLessThan(0.01);
      }
    }
  });

  it("a 0.6 s stop 2.5 cm above the start IS the same rest (fails if the constant is halved): the rep ends there, 2.5 cm short", () => {
    // measured: durationS 1.83 to 1.85, W- -5.6 to -5.1 % (2.5 cm of 50), W+ and ROM untouched
    for (const [noiseM, seedList] of NOISE) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs: stopAbove(0.025), noiseM, seed })).reps[0]!;
        expect(Math.abs(rep.durationS - 1.833)).toBeLessThan(0.035);
        expect(relErr(-rep.negativeWorkJ, MG * 0.475)).toBeLessThan(0.01);
        expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.01);
      }
    }
  });

  it("a 0.6 s stop 1 cm above the start is the same rest too: the rep ends there, 1 cm short", () => {
    // measured: durationS 1.83 to 1.87, W- -2.5 to -2.1 %
    for (const [noiseM, seedList] of NOISE) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs: stopAbove(0.01), noiseM, seed })).reps[0]!;
        expect(Math.abs(rep.durationS - 1.85)).toBeLessThan(0.035);
        expect(relErr(-rep.negativeWorkJ, MG * 0.49)).toBeLessThan(0.01);
      }
    }
  });
});

describe("pauses are grouped by level, so a stop right at the 3 cm limit does not leave a stray candidate deep in the rest", () => {
  // Comparing each pause only with those already kept drops the part of a noisy rest that is within 3 cm of
  // an inner stop and keeps the part that is a hair further: an arbitrary instant seconds before the lift
  // (measured that way: start up to 2.25 s early, durationS up to 5.17 s). Grouped, the stop and the rest
  // are one level and the rep starts at the stop.
  it("a 0.6 s stop 3 cm above the rest on the way up, no noise and ±2 mm over 10 seeds: the rep starts at the stop, 3 cm short", () => {
    const legs: Leg[] = [[3, 0], [0.4, 0.03], [0.6, 0.03], [1, 0.5], [1, 0], [3, 0]];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs, noiseM, seed })).reps[0]!;
        expect(Math.abs(rep.startS - 4.075)).toBeLessThan(0.035); // measured 4.07 to 4.08 (the stop ends at 4.0 s)
        expect(Math.abs(rep.durationS - 1.85)).toBeLessThan(0.035); // measured 1.83 to 1.87
        expect(relErr(rep.positiveWorkJ, MG * 0.47)).toBeLessThan(0.01); // measured -6.5 to -6.1 % of m g 0.5
      }
    }
  });
});

describe("FILTER_LIMITED_LIFT_S = 0.65 s is bracketed by lifts either side of it", () => {
  it("is 0.65", () => {
    expect(FILTER_LIMITED_LIFT_S).toBe(0.65);
  });

  it("a 0.7 s lift of 0.5 m reads 0.617 s and is filterLimited (fails at 0.5)", () => {
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs: repLegs(3, 0.5, 0.7, 0.7, 1), noiseM, seed }));
        expect(r.reps).toHaveLength(3);
        for (const rep of r.reps) {
          expect(Math.abs(rep.liftDurationS - 0.617)).toBeLessThan(0.03); // measured 0.600 to 0.617
          expect(rep.filterLimited).toBe(true);
        }
      }
    }
  });

  it("a 0.9 s lift of 0.5 m reads 0.767 s and is not filterLimited (fails at 0.9)", () => {
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs: repLegs(3, 0.5, 0.9, 0.9, 1), noiseM, seed }));
        expect(r.reps).toHaveLength(3);
        for (const rep of r.reps) {
          expect(Math.abs(rep.liftDurationS - 0.767)).toBeLessThan(0.05); // measured 0.750 to 0.800
          expect(rep.filterLimited).toBe(false);
        }
      }
    }
  });

  it("a 0.8 s lift of 0.5 m, which reads within half a percent, is not filterLimited (it would be at the old 0.7)", () => {
    const r = analyze(legSession({ legs: repLegs(3, 0.5, 0.8, 0.8, 1) }));
    for (const rep of r.reps) {
      expect(Math.abs(rep.liftDurationS - 0.683)).toBeLessThan(0.02);
      expect(rep.filterLimited).toBe(false);
      expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.01);
    }
  });
});

describe("visibilityThreshold reaches the resampler, not just the quality gate", () => {
  const session = (): PoseFrame[] => syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: SCALE });
  /** Every 25th frame has the given visibility and a wristY 0.2 image units (0.5 m) off: garbage wherever it is used. */
  const withDoubtfulFrames = (visibility: number): PoseFrame[] => session().map((f, i) => (i % 25 === 7 ? { ...f, visibility, wristY: f.wristY - 0.2 } : f));
  const worstWorkErr = (r: Extract<SessionResult, { ok: true }>): number => Math.max(...r.reps.map((rep) => relErr(rep.positiveWorkJ, MG * 0.5)));

  it("frames at visibility 0.45 carrying garbage: clean at the default threshold and at 0.5, visibly wrong at 0.3", () => {
    const frames = withDoubtfulFrames(0.45);
    for (const options of [{}, { visibilityThreshold: 0.5 }]) {
      const clean = analyze(frames, options);
      expect(clean.reps).toHaveLength(3);
      expect(worstWorkErr(clean)).toBeLessThan(0.01); // measured 0.5 %
      expect(clean.quality.lowVisibilityFraction).toBeGreaterThan(0.03);
    }
    // at 0.3 the same frames are trusted: the gate counts none as lost and their garbage is in the trace
    const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE, visibilityThreshold: 0.3 });
    expect(r.quality.lowVisibilityFraction).toBe(0);
    const dirty = r.ok ? (r.reps.length === 3 ? worstWorkErr(r) : Number.POSITIVE_INFINITY) : Number.POSITIVE_INFINITY;
    expect(dirty).toBeGreaterThan(0.2); // measured: the rep count or the work is far off
  });

  it("frames at visibility 0.55 carrying garbage: wrong at the default threshold, clean when the caller raises it to 0.6", () => {
    const frames = withDoubtfulFrames(0.55);
    const strict = analyze(frames, { visibilityThreshold: 0.6 });
    expect(strict.reps).toHaveLength(3);
    expect(worstWorkErr(strict)).toBeLessThan(0.01);
    const lax = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE });
    const dirty = lax.ok ? (lax.reps.length === 3 ? worstWorkErr(lax) : Number.POSITIVE_INFINITY) : Number.POSITIVE_INFINITY;
    expect(dirty).toBeGreaterThan(0.2);
  });
});

describe("known failure modes of the rep window (pins of what the README states, not goals)", () => {
  it("a stop on the way up AND one at the same height on the way down reads as a rack: only the upper half is measured, and trimmedRangeFraction is 0.5", () => {
    const legs: Leg[] = [[2, 0], [0.5, 0.25], [0.35, 0.25], [0.5, 0.5], [0.5, 0.25], [0.35, 0.25], [0.5, 0], [2, 0]];
    const rep = analyze(legSession({ legs })).reps[0]!;
    expect(relErr(rep.rangeOfMotionM, 0.25)).toBeLessThan(0.02); // measured 0.249
    expect(Math.abs(rep.trimmedRangeFraction - 0.5)).toBeLessThan(0.01);
  });

  it("a stop on the way up in a rep that returns only to +0.15 m: the stop at 0.25 m is nearer the return height than the start is, and wins", () => {
    const legs: Leg[] = [[2, 0], [0.5, 0.25], [0.35, 0.25], [0.5, 0.5], [1, 0.15], [3, 0.15]];
    const rep = analyze(legSession({ legs })).reps[0]!;
    expect(relErr(rep.rangeOfMotionM, 0.25)).toBeLessThan(0.02);
    expect(Math.abs(rep.trimmedRangeFraction - 0.5)).toBeLessThan(0.01);
    expect(relErr(-rep.negativeWorkJ, MG * 0.35)).toBeLessThan(0.01); // the lowering is whole
  });

  it("set-down with no pause before it is billed to the last rep: W- +120 % (separate leg) and +178 % (one movement to the floor)", () => {
    const separate: Leg[] = [[2, 0], [1, 0.5], [1, 0], [1, 0], [1, 0.5], [1, 0], [1.2, -0.6], [0.5, -0.6], [1, 0], [1, 0]];
    const oneLeg: Leg[] = [[2, 0], [1, 0.5], [1, 0], [1, 0], [1, 0.5], [2, -0.6], [0.5, -0.6], [1, 0], [1, 0]];
    const a = analyze(legSession({ legs: separate }));
    expect(a.reps).toHaveLength(2);
    expect(relErr(-a.reps[0]!.negativeWorkJ, MG * 0.5)).toBeLessThan(0.01); // the rep before it is untouched
    expect(-a.reps[1]!.negativeWorkJ / (MG * 0.5)).toBeGreaterThan(2.1); // measured 2.198
    expect(-a.reps[1]!.negativeWorkJ / (MG * 0.5)).toBeLessThan(2.3);
    expect(relErr(a.reps[1]!.positiveWorkJ, MG * 0.5)).toBeLessThan(0.01); // the lift of the last rep is right
    const b = analyze(legSession({ legs: oneLeg }));
    expect(b.reps).toHaveLength(2);
    // the truth for the one-leg lowering is the first 0.5 m of a 1.1 m descent; the whole descent reads 2.2 × m g × 0.5
    expect(-b.reps[1]!.negativeWorkJ / (MG * 0.5)).toBeGreaterThan(2.1);
    expect(-b.reps[1]!.negativeWorkJ / (MG * 0.5)).toBeLessThan(2.3);
  });

  it("pick-up straight into the first curl, with no pause: ROM and W+ +120 %", () => {
    const legs: Leg[] = [[1, 0], [1, -0.6], [0.5, -0.6], [1.2, 0], [1, 0.5], [1, 0], [2, 0]];
    const r = analyze(legSession({ legs }));
    expect(r.reps).toHaveLength(1);
    expect(r.reps[0]!.rangeOfMotionM / 0.5).toBeGreaterThan(2.1); // measured 2.198
    expect(r.reps[0]!.rangeOfMotionM / 0.5).toBeLessThan(2.3);
    expect(r.reps[0]!.positiveWorkJ / (MG * 0.5)).toBeGreaterThan(2.1);
    expect(relErr(-r.reps[0]!.negativeWorkJ, MG * 0.5)).toBeLessThan(0.01); // the lowering stops at the rest, as it should
  });
});
