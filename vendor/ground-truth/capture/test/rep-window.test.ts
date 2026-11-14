import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { legSession, repLegs, type Leg } from "./helpers";

// How the pauses that bound a rep are CHOSEN (round 3). A pause can bound a rep only if it lies below
// the movement and its level half is actually at rest; of the pauses that qualify, the pair whose rest
// levels agree is taken, because a rep starts from and returns to roughly the same height.
// Every scenario here failed on the previous rule (latest pause below the top plateau), which read
// slow movement as a pause and a hesitation as the start of the rep. The numbers in the comments are
// measured on synthetic signals at 60 Hz.

const SCALE = 2.5;
const MASS_KG = 10;
const EARTH = G_ENV_MS2.EARTH;
const MG = MASS_KG * EARTH;

function analyze(frames: readonly PoseFrame[]): Extract<SessionResult, { ok: true }> {
  const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE });
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

const relErr = (actual: number, expected: number): number => Math.abs(actual - expected) / Math.abs(expected);
const seeds = (n: number): number[] => Array.from({ length: n }, (_, i) => i + 1);

describe("R1: slow movement is not a pause", () => {
  // Previous rule: 0.5 m over 8 s read -95.7 %, 0.3 m over 6 s -92.4 %, 0.25 m over 5 s -90.7 %, 0.15 m over 4 s -84.3 %.
  // Now -2.2 %, -3.2 %, -3.4 % and -5.5 % (work and ROM alike): what is left is the slow first and last
  // centimetres, which move under the 2 cm/s floor and are trimmed with the rests. Bounds are twice the measurement.
  for (const [heightM, tS, bound] of [[0.5, 8, 0.045], [0.3, 6, 0.065], [0.25, 5, 0.07], [0.15, 4, 0.11]] as const) {
    it(`${heightM} m over ${tS} s up and down, 3 s rests: 2 reps, work and ROM within ${(bound * 100).toFixed(1)} %`, () => {
      const r = analyze(legSession({ legs: repLegs(2, heightM, tS, tS, 3) }));
      expect(r.reps).toHaveLength(2);
      for (const rep of r.reps) {
        expect(relErr(rep.positiveWorkJ, MG * heightM)).toBeLessThan(bound);
        expect(relErr(-rep.negativeWorkJ, MG * heightM)).toBeLessThan(bound);
        expect(relErr(rep.rangeOfMotionM, heightM)).toBeLessThan(bound);
      }
    });
  }

  // Previous rule: the slow half lost 89 % (W- for a slow lowering, W+ and ROM for a slow lift).
  // Now the 1 s half reads -1.4 % and the 5 s half -4.7 % (bounds 3 % and 9.5 %).
  for (const [upS, downS] of [[1, 5], [5, 1]] as const) {
    it(`0.2 m, ${upS} s up and ${downS} s down: the fast half within 3 %, the slow half within 9.5 %`, () => {
      const r = analyze(legSession({ legs: repLegs(1, 0.2, upS, downS, 3) }));
      expect(r.reps).toHaveLength(1);
      const rep = r.reps[0]!;
      expect(relErr(rep.positiveWorkJ, MG * 0.2)).toBeLessThan(upS === 1 ? 0.03 : 0.095);
      expect(relErr(-rep.negativeWorkJ, MG * 0.2)).toBeLessThan(downS === 1 ? 0.03 : 0.095);
      expect(relErr(rep.rangeOfMotionM, 0.2)).toBeLessThan(upS === 1 ? 0.03 : 0.095); // ROM is the lift's
    });
  }
});

describe("R2: a stop inside a lift or a lowering does not split the rep", () => {
  // A sticking point half-way has no pause at its height on the other side of the top, so the bottom
  // rests, whose levels agree, bound the rep. Previous rule: ROM and W+ -50 % (stop on the way up),
  // W- -50 % (stop on the way down), for a 0.2 s stop as much as for a 0.35 s one. Now, worst over the
  // no-noise run and ten seeds at ±2 mm: work 0.79 %, ROM 0.37 % (bounds 2 % and 1 %).
  for (const stopS of [0.2, 0.35]) {
    const up: Leg[] = [[2, 0], [0.5, 0.25], [stopS, 0.25], [0.5, 0.5], [1, 0], [2, 0]];
    const down: Leg[] = [[2, 0], [1, 0.5], [0.5, 0.25], [stopS, 0.25], [0.5, 0], [2, 0]];
    for (const [name, legs] of [["up", up], ["down", down]] as const) {
      it(`0.5 m with a ${stopS} s stop at 0.25 m on the way ${name}: ROM within 1 %, both works within 2 %`, () => {
        for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
          for (const seed of seedList) {
            const r = analyze(legSession({ legs, noiseM, seed }));
            expect(r.reps).toHaveLength(1);
            const rep = r.reps[0]!;
            expect(relErr(rep.rangeOfMotionM, 0.5)).toBeLessThan(0.01);
            expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.02);
            expect(relErr(-rep.negativeWorkJ, MG * 0.5)).toBeLessThan(0.02);
            expect(rep.trimmedRangeFraction).toBeGreaterThan(0.98);
          }
        }
      });
    }
  }
});

describe("R3: lift duration with a pause at the top", () => {
  // The lift ends at the FIRST sample within ONSET_TOLERANCE_M of the top's level, not at the plateau's
  // highest sample, which noise places anywhere in the plateau (a 1 s lift with a 1 s top pause read
  // 0.92 to 1.93 s over 50 seeds).
  // Measured: a 1 s, 0.5 m lift reads 0.850 s whatever the pause (3 mm left out at each end), and 0.833 to
  // 0.867 s over ten seeds at ±2 mm (0.833 to 0.883 over a hundred): one 60 Hz sample either way, bound 0.05 s.
  const NO_NOISE_LIFT_S = 0.85;
  for (const pauseS of [0.3, 1, 3]) {
    it(`1 s lift, ${pauseS} s pause at the top, ±2 mm, 10 seeds: liftDurationS within 0.05 s of the no-noise value on every seed`, () => {
      const legs: Leg[] = [[2, 0], [1, 0.5], [pauseS, 0.5], [1, 0], [2, 0]];
      const clean = analyze(legSession({ legs })).reps[0]!;
      expect(Math.abs(clean.liftDurationS - NO_NOISE_LIFT_S)).toBeLessThan(0.02);
      for (const seed of seeds(10)) {
        const r = analyze(legSession({ legs, noiseM: 0.002, seed }));
        expect(r.reps).toHaveLength(1);
        expect(Math.abs(r.reps[0]!.liftDurationS - clean.liftDurationS)).toBeLessThan(0.05);
        expect(r.reps[0]!.filterLimited).toBe(false);
      }
    });
  }

  it("0.4 s lift with a 3 s pause at the top reads 0.383 s and is filterLimited on every seed (it read 3.35 s and false)", () => {
    const legs: Leg[] = [[2, 0], [0.4, 0.5], [3, 0.5], [0.4, 0], [2, 0]];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs, noiseM, seed }));
        expect(r.reps).toHaveLength(1);
        expect(Math.abs(r.reps[0]!.liftDurationS - 0.383)).toBeLessThan(0.035); // measured 0.383 on every seed
        expect(r.reps[0]!.filterLimited).toBe(true);
      }
    }
  });
});

describe("trimmedRangeFraction: how much of the detected movement was measured", () => {
  it("is about 1 for an ordinary rep between two rests", () => {
    const r = analyze(legSession({ legs: repLegs(3, 0.5, 1, 1, 3) }));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      expect(rep.trimmedRangeFraction).toBeGreaterThan(0.98);
      expect(rep.trimmedRangeFraction).toBeLessThanOrEqual(1);
    }
  });

  it("is about 0.45 for the first curl after a floor pick-up (0.5 m measured of the 1.1 m the segmenter saw)", () => {
    const PICKUP: Leg[] = [
      [1, 0], [1, -0.6], [0.5, -0.6], [1.2, 0], [1.5, 0],
      [1, 0.5], [1, 0], [1, 0],
      [1, 0.5], [1, 0], [1, 0],
      [1, 0.5], [1, 0], [1.5, 0],
      [1.2, -0.6], [0.5, -0.6], [1, 0], [1, 0],
    ];
    const r = analyze(legSession({ legs: PICKUP }));
    expect(r.reps).toHaveLength(3);
    expect(Math.abs(r.reps[0]!.trimmedRangeFraction - 0.5 / 1.1)).toBeLessThan(0.01);
    expect(r.reps[1]!.trimmedRangeFraction).toBeGreaterThan(0.98);
    expect(Math.abs(r.reps[2]!.trimmedRangeFraction - 0.5 / 1.1)).toBeLessThan(0.01); // the set-down after the last curl
  });
});

describe("rest levels agree to the band that defines a pause, not to the last millimetre", () => {
  // Exact agreement does not exist: the levels inside one rest differ by fractions of a millimetre, and
  // the closest pair is then an arbitrary one deep inside the rests (measured with exact minimisation at
  // ±2 mm: start up to 8.9 s early with 10 s rests, work +7.8 %). Pairs within DWELL_BAND_M of the best
  // agreement are equal, and the smallest window wins.
  it("10 s rests, no noise and ±2 mm: each rep starts within 0.1 s of the lift and takes 2 s less the trimmed ends", () => {
    for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(5)]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs: repLegs(3, 0.5, 1, 1, 10), noiseM, seed }));
        expect(r.reps).toHaveLength(3);
        r.reps.forEach((rep, k) => {
          expect(Math.abs(rep.startS - (10 + 12 * k) - 0.083)).toBeLessThan(0.035); // measured 0.067 to 0.100 late
          expect(Math.abs(rep.durationS - 1.85)).toBeLessThan(0.07); // measured 1.817 to 1.867
        });
      }
    }
  });

  // (Since pauses are grouped by level, one rest offers one candidate and these two scenarios are held by
  // the grouping as well: see wobble.test.ts.)
  // A hand that drifts while it rests. It rises 2 cm during each rest and the rep comes back 1 cm lower
  // than it started, so somewhere inside the rest there is a window at exactly the return height. With a
  // tolerance of ONSET_TOLERANCE_M that window won: start 1.9 to 2.3 s early, a 1 s lift reported as 3.2 s.
  for (const [name, legs] of [
    ["rises 2 cm during the rest, rep returns 1 cm low", [[5, 0.02], [1, 0.52], [1, 0.01], [5, 0.03], [1, 0.53], [1, 0.02], [5, 0.04]]],
    ["sinks 2 cm during the rest, rep returns 1 cm high", [[5, -0.02], [1, 0.48], [1, -0.01], [5, -0.03], [1, 0.47], [1, -0.02], [5, -0.04]]],
  ] as const) {
    it(`the hand ${name}: the rep still starts at the lift (within 0.12 s) and lasts 2 s (within 0.2 s)`, () => {
      for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
        for (const seed of seedList) {
          const r = analyze(legSession({ legs: legs as unknown as Leg[], noiseM, seed }));
          expect(r.reps).toHaveLength(2);
          r.reps.forEach((rep, k) => {
            expect(Math.abs(rep.startS - (5 + 7 * k))).toBeLessThan(0.12); // measured 0.067 to 0.083 late
            expect(Math.abs(rep.durationS - 2)).toBeLessThan(0.2); // measured 0.13 to 0.17 short
            expect(Math.abs(rep.liftDurationS - 0.85)).toBeLessThan(0.05);
            expect(relErr(rep.positiveWorkJ, MG * 0.5)).toBeLessThan(0.015); // measured 0.6 %
          });
        }
      }
    });
  }
});
