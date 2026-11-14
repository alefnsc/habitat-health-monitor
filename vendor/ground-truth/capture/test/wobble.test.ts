import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { lcg, legSession, repLegs, type Leg } from "./helpers";

// One candidate per rest level. A hand that wobbles or sways while it rests leaves only scattered
// pauses inside the rest, at levels that differ by more than the agreement band. Pair matching then
// reached for a distant pair that happened to agree, and the rep swallowed the rest: with a 1 cm
// wobble at 2.5 Hz, positive work +17 % after 1 s rests, +74 % after 4 s, +178 % after 10 s, with
// startS 0.00 and trimmedRangeFraction 1.000. Two pauses on the same side of the top whose levels are
// within 2 × DWELL_BAND_M are the same rest seen twice: only the one nearest the top is a candidate.
// Numbers in comments are measured on synthetic signals at 60 Hz.

const SCALE = 2.5;
const MASS_KG = 10;
const EARTH = G_ENV_MS2.EARTH;
const MG = MASS_KG * EARTH;
const PHASES = [0, 1, 2, 3, 4, 5, 6, 7]; // eighths of a turn

function analyze(frames: readonly PoseFrame[], over: Partial<Parameters<typeof analyzeSession>[1]> = {}): Extract<SessionResult, { ok: true }> {
  const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE, ...over });
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

/** `frames` with a sinusoid of the given AMPLITUDE (half the peak-to-peak) added to the height throughout, and optional noise. */
function withOscillation(frames: PoseFrame[], amplitudeM: number, hz: number, phase: number, noiseM = 0, seed = 1): PoseFrame[] {
  const noise = lcg(seed);
  return frames.map((f) => ({ ...f, wristY: f.wristY - (amplitudeM * Math.sin(2 * Math.PI * hz * f.tS + (phase * Math.PI) / 4) + noiseM * noise()) / SCALE }));
}

const relErr = (actual: number, expected: number): number => Math.abs(actual - expected) / Math.abs(expected);

describe("a wobble of 1 cm amplitude (2 cm peak to peak) throughout does not stretch a rep into its rests", () => {
  // Measured after the fix, over the 8 phases and the 3 reps: W+ -3.2 to +4.6 % (the wobble itself rides on the
  // lift and is real movement), durationS 1.90 to 2.50 s (1.83 s without the wobble), the same for every rest
  // length. Bounds: 9 % and 2.9 s. Before: +17 % / 4.0 s (1 s rests), +74 % / 10 s (4 s), +186 % / 22 s (10 s) at
  // 2.5 and 3 Hz. The rule before pair matching (19f5c2e) read +8.9 % / 2.6 s at 2.5 Hz and +93 % / 12 s at 3 Hz.
  // At 1.5 Hz the rep was already within these bounds: that row is a regression pin, not a red-first test.
  for (const hz of [1.5, 2.5, 3]) {
    for (const restS of [1, 4, 10]) {
      it(`${hz} Hz, ${restS} s rests, 8 phases: W+ within 9 %, durationS between 1.7 and 2.9 s, startS within 0.45 s`, () => {
        for (const phase of PHASES) {
          const r = analyze(withOscillation(legSession({ legs: repLegs(3, 0.5, 1, 1, restS) }), 0.01, hz, phase));
          expect(r.reps).toHaveLength(3);
          r.reps.forEach((rep, k) => {
            expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.09);
            expect(rep.durationS).toBeGreaterThan(1.7);
            expect(rep.durationS).toBeLessThan(2.9);
            expect(Math.abs(rep.startS - (restS + k * (2 + restS)))).toBeLessThan(0.45); // measured 0.25 s early to 0.17 s late
          });
        }
      });
    }
  }

  it("with ±2 mm of noise on top (4 s rests, 2 seeds per phase): W+ within 20 %, durationS under 3.5 s", () => {
    // Measured worst: 1.5 Hz +5.2 % / 2.52 s, 2.5 Hz +5.8 % / 2.33 s, 3 Hz +11.3 % / 2.90 s.
    // Before: +11.8 % / 3.17 s, +73.7 % / 10 s, +30.7 % / 5 s. Rule 19f5c2e: +6.1 % / 2.15 s, +33.2 % / 5.4 s, +19.2 % / 3.8 s.
    for (const hz of [1.5, 2.5, 3]) {
      for (const phase of PHASES) {
        for (const seed of [1, 2]) {
          const r = analyze(withOscillation(legSession({ legs: repLegs(3, 0.5, 1, 1, 4) }), 0.01, hz, phase, 0.002, seed));
          expect(r.reps).toHaveLength(3);
          for (const rep of r.reps) {
            expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.2);
            expect(rep.durationS).toBeLessThan(3.5);
          }
        }
      }
    }
  });
});

describe("a slow sway at 0.2 Hz under the reps (5 s rests, 8 phases)", () => {
  // The numbers depend on where in the sway the lift begins, so all eight phases are swept.
  // 1 cm amplitude (2 cm peak to peak): durationS 1.80 to 1.92 s (it reached 3.08 s before).
  // 2 cm amplitude (4 cm peak to peak): 1.78 to 3.02 s (it reached 4.17 s before; rule 19f5c2e 1.77 to 2.03 s).
  // What is left at 2 cm: the hand moves faster than the 2 cm/s floor as the lift begins, so the nearest
  // pause can be half a second back. W+ is -5.6 to +5.4 % whatever the rule: the sway's own travel.
  for (const [amplitudeM, maxDurationS] of [[0.01, 2.05], [0.02, 3.5]] as const) {
    for (const noiseM of [0, 0.002]) {
      it(`${amplitudeM * 100} cm amplitude, ±${noiseM * 1000} mm: durationS between 1.7 and ${maxDurationS} s`, () => {
        for (const phase of PHASES) {
          for (const seed of noiseM === 0 ? [1] : [1, 2, 3]) {
            const r = analyze(withOscillation(legSession({ legs: repLegs(3, 0.5, 1, 1, 5) }), amplitudeM, 0.2, phase, noiseM, seed));
            expect(r.reps).toHaveLength(3);
            for (const rep of r.reps) {
              expect(rep.durationS).toBeGreaterThan(1.7);
              expect(rep.durationS).toBeLessThan(maxDurationS);
            }
          }
        }
      });
    }
  }
});

describe("the pieces of the rule, each held by a scenario", () => {
  it("a pause AT the top is not the start of the lift, even when the bottom rest is too short to be a pause (onset side)", () => {
    // 0.2 s at the bottom is no pause, so the only pause before the top's highest sample is the top's own plateau.
    const legs: Leg[] = [[0.2, 0], [1, 0.5], [1.5, 0.5], [1, 0], [2, 0]];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, [1, 2, 3, 4, 5]]] as const) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs, noiseM, seed })).reps[0]!;
        expect(relErr(rep.rangeOfMotionM, 0.5)).toBeLessThan(0.02);
        expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.03);
      }
    }
  });

  it("a pause AT the top is not the end of the lowering, even when nothing follows the lowering (offset side)", () => {
    const legs: Leg[] = [[2, 0], [1, 0.5], [1.5, 0.5], [1, 0], [0.2, 0]];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, [1, 2, 3, 4, 5]]] as const) {
      for (const seed of seedList) {
        const rep = analyze(legSession({ legs, noiseM, seed })).reps[0]!;
        expect(relErr(-rep.negativeWorkJ, MG * 0.5)).toBeLessThan(0.03);
        expect(rep.durationS).toBeGreaterThan(3.2); // lift, 1.5 s at the top, lowering
      }
    }
  });

  it("the rest level is the median of the still half, not its first sample: one outlying sample does not move the boundary", () => {
    // ±5 mm of noise leaves about ±1 mm in the smoothed rest; a level read off a single sample moves the 3 mm
    // boundary with it. Over 20 seeds the start stays within 0.135 s and the work within 1.9 %.
    for (let seed = 1; seed <= 20; seed++) {
      const r = analyze(legSession({ legs: repLegs(3, 0.5, 1, 1, 5), noiseM: 0.005, seed }));
      expect(r.reps).toHaveLength(3);
      r.reps.forEach((rep, k) => {
        expect(Math.abs(rep.startS - (5 + 7 * k))).toBeLessThan(0.135);
        expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.019);
      });
    }
  });

  it("minPhaseDisplacementM reaches the rep window: with 0.3 m, a pause 0.2 m under the top is too near it to bound the rep", () => {
    // Rack at 0.3 m, press to 0.5 m, back to the rack, down. With the default 0.1 m the rack pauses bound a
    // 0.2 m press; with 0.3 m they are within the threshold of the top, and the rep is the whole 0.5 m.
    const legs: Leg[] = [[2, 0], [1, 0.3], [1, 0.3], [1, 0.5], [1, 0.3], [1, 0.3], [1, 0], [2, 0]];
    const press = analyze(legSession({ legs })).reps;
    expect(press).toHaveLength(1);
    expect(relErr(press[0]!.rangeOfMotionM, 0.2)).toBeLessThan(0.03);
    const whole = analyze(legSession({ legs }), { minPhaseDisplacementM: 0.3 }).reps;
    expect(whole).toHaveLength(1);
    expect(relErr(whole[0]!.rangeOfMotionM, 0.5)).toBeLessThan(0.02);
    expect(relErr(whole[0]!.positiveWorkJ, MG * 0.5)).toBeLessThan(0.02);
  });
});
