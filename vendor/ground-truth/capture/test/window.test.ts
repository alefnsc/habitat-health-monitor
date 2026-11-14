import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { ONSET_TOLERANCE_M, analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { legSession, repLegs, syntheticSession, type Leg } from "./helpers";

// A rep's work window is its movement, from where the position leaves the rest level before the
// top to where it reaches the rest level after it. Rests, pick-ups and set-downs are not part of a rep.
//
// Timing. The boundary is the last (first) pause sample within ONSET_TOLERANCE_M = 3 mm of the rest
// level, and a minimum-jerk lift of 0.5 m in 1 s takes 0.08 s to cover its first 3 mm, so the onset
// reads 0.07 to 0.12 s late and the offset about as early: durationS reads 0.10 to 0.20 s short for a
// 2 s rep. Both tolerances are the worst value over 30 seeds at ±5 mm (5 and 10 s rests) plus one 60 Hz
// sample: startS 0.117 + 0.017, durationS 0.200 + 0.017.
const START_TOLERANCE_S = 0.135;
const DURATION_TOLERANCE_S = 0.22;
const SEEDS_30 = Array.from({ length: 30 }, (_, i) => i + 1);
const SEEDS_10 = SEEDS_30.slice(0, 10);

const SCALE = 2.5;
const MASS_KG = 10;
const EARTH = G_ENV_MS2.EARTH;
const TRUE_WORK_J = MASS_KG * EARTH * 0.5; // 49.05
const TRUE_ROM_M = 0.5;
const TRUE_DURATION_S = 2; // 1 s up, 1 s down

function analyze(frames: readonly PoseFrame[]): Extract<SessionResult, { ok: true }> {
  const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE });
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

const relErr = (actual: number, expected: number): number => Math.abs(actual - expected) / Math.abs(expected);

describe("rests are not billed to a rep", () => {
  // Rest noise rectifies into positive work (0.22 J/s at ±2 mm, 0.54 J/s at ±5 mm for 10 kg on Earth),
  // so a rep that owns its rests reads 7 to 19 % high after a 10 s rest.
  for (const restS of [5, 10]) {
    // Work bounds are twice the worst value over the 30 seeds and both rest lengths: 0.72 % at ±2 mm, 1.11 % at ±5 mm.
    for (const [noiseM, workTolerance] of [[0.002, 0.014], [0.005, 0.022]] as const) {
      it(`3 reps, ${restS} s rests, ±${noiseM * 1000} mm, 30 seeds: work within ${workTolerance * 100} %, start within ${START_TOLERANCE_S} s, duration within ${DURATION_TOLERANCE_S} s`, () => {
        for (const seed of SEEDS_30) {
          const r = analyze(syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS, rateHz: 60, noiseM, seed, metersPerUnit: SCALE }));
          expect(r.reps).toHaveLength(3);
          r.reps.forEach((rep, k) => {
            expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(workTolerance);
            expect(relErr(-rep.negativeWorkJ, TRUE_WORK_J)).toBeLessThan(workTolerance);
            expect(Math.abs(rep.startS - (restS + k * (TRUE_DURATION_S + restS)))).toBeLessThan(START_TOLERANCE_S);
            expect(Math.abs(rep.durationS - TRUE_DURATION_S)).toBeLessThan(DURATION_TOLERANCE_S);
          });
        }
      });
    }
  }

  it("impulse of the same rep does not depend on the rest around it: 0.5 s and 10 s rests agree within 2 %", () => {
    const at = (restS: number) =>
      analyze(syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS, rateHz: 60, noiseM: 0.002, seed: 1, metersPerUnit: SCALE }));
    const short = at(0.5).reps[1]!;
    const long = at(10).reps[1]!;
    expect(relErr(long.impulseNs, short.impulseNs)).toBeLessThan(0.02); // measured 1.0 % (178.05 and 179.86 N·s: one sample of duration)
  });
});

describe("rep boundaries sit at the rest level, not at the edge of the pause", () => {
  // The pause detector's band (DWELL_BAND_M = 1.5 cm) is wider than the movement's first and last
  // centimetres, so placing the boundary at the pause's edge costs the rep those centimetres: a
  // systematic -3.2 % in work and -2.6 % in range of motion for a 0.5 m rep, twice that at 0.25 m.
  // The boundary belongs where the position leaves the rest level (ONSET_TOLERANCE_M), not the band.
  const TRUE_START = (restS: number, k: number): number => restS + k * (TRUE_DURATION_S + restS);
  const rests = (heightM: number, restS: number, noiseM: number, seed: number) =>
    analyze(syntheticSession({ reps: 3, heightM, upS: 1, downS: 1, restS, rateHz: 60, noiseM, seed, metersPerUnit: SCALE }));

  it("ONSET_TOLERANCE_M is the 3 mm judgement call, exported and not tuned", () => {
    expect(ONSET_TOLERANCE_M).toBe(0.003);
  });

  it("0.5 m, 5 s rests, no noise: work within 1.5 %, ROM within 1 %, start within 0.10 s, duration within 0.20 s", () => {
    const r = rests(0.5, 5, 0, 1);
    expect(r.reps).toHaveLength(3);
    r.reps.forEach((rep, k) => {
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.015);
      expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.01);
      expect(Math.abs(rep.startS - TRUE_START(5, k))).toBeLessThan(0.1);
      expect(Math.abs(rep.durationS - TRUE_DURATION_S)).toBeLessThan(0.2);
    });
  });

  it("0.5 m, 5 s rests, ±2 mm (10 seeds): work within 1.1 %, ROM within 0.9 %", () => {
    // measured over the ten seeds: work 0.54 %, ROM 0.45 %. A boundary back at the pause's edge reads 3.2 % and 2.6 %.
    for (const seed of SEEDS_10) {
      const r = rests(0.5, 5, 0.002, seed);
      expect(r.reps).toHaveLength(3);
      for (const rep of r.reps) {
        expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.011);
        expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.009);
      }
    }
  });

  it("0.5 m, 10 s rests, ±5 mm (10 seeds): work within 1.9 %", () => {
    // measured over the ten seeds: 0.93 %
    for (const seed of SEEDS_10) {
      const r = rests(0.5, 10, 0.005, seed);
      expect(r.reps).toHaveLength(3);
      for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.019);
    }
  });

  it("0.25 m, 5 s rests, no noise: work within 2.5 % of 24.525 J (the bias does not grow as the movement gets shorter)", () => {
    const r = rests(0.25, 5, 0, 1);
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, MASS_KG * EARTH * 0.25)).toBeLessThan(0.025);
  });

  it("pick-up, 1.5 s pause, three curls, set-down: each rep's work within 1.1 % and ROM within 0.95 % (no noise, and ±2 mm over 10 seeds)", () => {
    // measured: work 0.46 % and ROM 0.37 % with no noise, 0.55 % and 0.47 % worst over the ten seeds
    const PICKUP: Leg[] = [
      [1, 0], [1, -0.6], [0.5, -0.6], [1.2, 0], [1.5, 0],
      [1, 0.5], [1, 0], [1, 0],
      [1, 0.5], [1, 0], [1, 0],
      [1, 0.5], [1, 0], [1.5, 0],
      [1.2, -0.6], [0.5, -0.6], [1, 0], [1, 0],
    ];
    for (const [noiseM, seedList] of [[0, [1]], [0.002, SEEDS_10]] as const) {
      for (const seed of seedList) {
        const r = analyze(legSession({ legs: PICKUP, noiseM, seed }));
        expect(r.reps).toHaveLength(3);
        for (const rep of r.reps) {
          expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.011);
          expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.0095);
        }
      }
    }
  });
});

describe("pick-up, set-down and a staged start are not part of a rep", () => {
  // Floor at −0.6 m, hang position 0, three curls of 0.5 m, 1.5 s pause at the hang before and after.
  const PICKUP: Leg[] = [
    [1, 0], [1, -0.6], [0.5, -0.6], [1.2, 0], [1.5, 0], // stand, reach the floor, grip, stand up with it, pause
    [1, 0.5], [1, 0], [1, 0], // curl 1 starts at 5.2 s
    [1, 0.5], [1, 0], [1, 0], // curl 2 starts at 8.2 s
    [1, 0.5], [1, 0], [1.5, 0], // curl 3 starts at 11.2 s
    [1.2, -0.6], [0.5, -0.6], [1, 0], [1, 0], // set it down, let go, stand up
  ];

  it("floor pick-up, 1.5 s pause, three 0.5 m curls, set-down: 3 reps, each ROM within 5 % and work within 8 %", () => {
    for (const noiseM of [0, 0.002]) {
      const r = analyze(legSession({ legs: PICKUP, noiseM }));
      expect(r.reps).toHaveLength(3);
      r.reps.forEach((rep, k) => {
        expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.05);
        expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.08);
        expect(relErr(-rep.negativeWorkJ, TRUE_WORK_J)).toBeLessThan(0.08);
        expect(Math.abs(rep.startS - (5.2 + 3 * k))).toBeLessThan(0.3);
      });
    }
  });

  it("rack to shoulders (+0.4 m), pause, then two 0.5 m presses and an un-rack: 2 reps, ROM within 5 %, work within 8 %", () => {
    const RACK: Leg[] = [[1, 0], [1, 0.4], [1.5, 0.4], [1, 0.9], [1, 0.4], [1, 0.4], [1, 0.9], [1, 0.4], [1.5, 0.4], [1, 0], [1, 0]];
    for (const noiseM of [0, 0.002]) {
      const r = analyze(legSession({ legs: RACK, noiseM }));
      expect(r.reps).toHaveLength(2);
      for (const rep of r.reps) {
        expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.05);
        expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.08);
        expect(relErr(-rep.negativeWorkJ, TRUE_WORK_J)).toBeLessThan(0.08);
      }
    }
  });
});

describe("a sub-threshold movement between two reps", () => {
  // 0.08 m is under the 0.10 m threshold, so it is not a rep. Two pauses of at least 0.5 s
  // separate it from the reps either side, so neither rep may take its work.
  const PARTIAL: Leg[] = [[1, 0], [1, 0.5], [1, 0], [0.6, 0], [0.5, 0.08], [0.5, 0], [0.6, 0], [1, 0.5], [1, 0], [1, 0]];

  it("is attributed to neither rep: both full reps within 5 % work", () => {
    for (const noiseM of [0, 0.002, 0.005]) {
      const r = analyze(legSession({ legs: PARTIAL, noiseM }));
      expect(r.reps).toHaveLength(2);
      for (const rep of r.reps) {
        expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.05);
        expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.05);
      }
    }
  });
});

describe("turnarounds", () => {
  it("a 1 s pause at the top does not end the lift early: the lift is still about 1 s and ROM is the full 0.5 m", () => {
    const legs: Leg[] = [[2, 0], [1, 0.5], [1, 0.5], [1, 0], [2, 0]];
    for (const noiseM of [0, 0.002]) {
      const r = analyze(legSession({ legs, noiseM }));
      expect(r.reps).toHaveLength(1);
      const rep = r.reps[0]!;
      expect(Math.abs(rep.liftDurationS - 0.85)).toBeLessThan(0.05); // the lift alone: it was 0.92 to 1.93 s while it ran to the plateau's highest sample
      expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.05);
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.05);
      expect(relErr(-rep.negativeWorkJ, TRUE_WORK_J)).toBeLessThan(0.05);
    }
  });

  it("reps with no rest between them: 3 reps, 2 s each, work within 2 %", () => {
    const r = analyze(syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 0, rateHz: 60, noiseM: 0.002, seed: 1, metersPerUnit: SCALE }));
    expect(r.reps).toHaveLength(3);
    r.reps.forEach((rep, k) => {
      // the junction between two 1 s lifts is borderline for a pause (0.29 s in band against 0.3 s), so a
      // rep may or may not be trimmed there; where it is, the junction is no true rest, but the boundary can
      // only fall between the movement and the pause's edge, so the error stays under the old 1.5 cm band
      // (measured work -0.6..+0.3 %, ROM -0.4..+0.4 %; the old boundary read the middle rep 3.0 % short)
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.02);
      expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.02);
      expect(Math.abs(rep.startS - 2 * k)).toBeLessThan(START_TOLERANCE_S);
      expect(Math.abs(rep.durationS - 2)).toBeLessThan(DURATION_TOLERANCE_S);
    });
  });

  it("reports the lift and the whole rep separately: liftDurationS is the lift alone", () => {
    const r = analyze(legSession({ legs: repLegs(3, 0.5, 1, 1.5, 3) }));
    for (const rep of r.reps) {
      expect(Math.abs(rep.liftDurationS - 0.85)).toBeLessThan(0.02); // measured 0.850: the lift ends 3 mm under the top (it was 0.917 to the top sample)
      expect(Math.abs(rep.durationS - 2.5)).toBeLessThan(0.3); // measured 2.30: 3 mm at each end count as rest, and the 1.5 s lowering takes longer to cover them
      expect(rep.liftDurationS).toBeLessThan(rep.durationS);
    }
  });
});
