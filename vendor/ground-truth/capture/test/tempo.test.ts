import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { lcg, legSession, repLegs } from "./helpers";

// How slow a movement may be. A pause must be still for half of DWELL_MIN_S to within ONSET_TOLERANCE_M,
// so anything slower than about 2 cm/s IS a rest to the rep window, and the slow first and last
// centimetres of a slow rep are trimmed with the rests. This file measures what that costs.
// All numbers are measured on synthetic signals at 60 Hz, 10 kg, Earth.

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

describe("height × tempo grid: minimum-jerk lift and lowering of the same duration, 3 s rests, no noise", () => {
  // Measured loss of work (positive, negative and range of motion agree to 0.1 point), in percent.
  // Columns: 1, 2, 4, 6 and 8 s per phase. The previous rule read -84 to -96 % in the six cells from
  // 0.15 m × 4 s, 0.25 m × 6 s and 0.5 m × 8 s on.
  const TEMPOS_S = [1, 2, 4, 6, 8] as const;
  const MEASURED_LOSS_PERCENT: Record<string, readonly number[]> = {
    "0.15": [1.3, 2.7, 5.5, 9.5, 15.0],
    "0.25": [0.8, 1.3, 2.7, 4.2, 6.1],
    "0.5": [0.5, 0.5, 1.1, 1.5, 2.2],
  };
  // Bound: twice the measurement, and never more than 20 %. The worst cell, 0.15 m over 8 s (peak speed
  // 3.5 cm/s), measures 15.0 % and is held to 20 %, not to 30 %: past 20 % it would be a finding.
  const boundOf = (lossPercent: number): number => Math.min(2 * lossPercent, 20) / 100;

  for (const heightM of [0.15, 0.25, 0.5]) {
    TEMPOS_S.forEach((tempoS, column) => {
      const loss = (MEASURED_LOSS_PERCENT[String(heightM)] as readonly number[])[column] as number;
      it(`${heightM} m over ${tempoS} s: 2 reps, work within ${(boundOf(loss) * 100).toFixed(1)} % (measured -${loss} %), and trimmedRangeFraction says how much was measured`, () => {
        const r = analyze(legSession({ legs: repLegs(2, heightM, tempoS, tempoS, 3) }));
        expect(r.reps).toHaveLength(2);
        for (const rep of r.reps) {
          expect(relErr(rep.positiveWorkJ, MG * heightM)).toBeLessThan(boundOf(loss));
          expect(relErr(-rep.negativeWorkJ, MG * heightM)).toBeLessThan(boundOf(loss));
          expect(relErr(rep.rangeOfMotionM, heightM)).toBeLessThan(boundOf(loss));
          // the error is a loss, never a gain (nothing of the rests is billed to the rep)
          expect(rep.positiveWorkJ).toBeLessThan(MG * heightM * 1.001);
          // and it is not silent: the fraction reported is the fraction measured (within 0.5 point)
          expect(Math.abs(rep.trimmedRangeFraction - rep.rangeOfMotionM / heightM)).toBeLessThan(0.005);
        }
      });
    });
  }

  it("with ±2 and ±5 mm of noise the loss grows in the slow, short cells, and trimmedRangeFraction still reports it (within 6 points)", () => {
    // Measured worst over 20 seeds, work: 0.15 m × 8 s -31.5 % at ±2 mm; 0.15 m × 6 s -31.7 % and 8 s -28.2 % at
    // ±5 mm; 0.25 m × 8 s -15.4 %; 0.5 m × 8 s -3.8 %. Those cells are a README limit, not a bound here: what is
    // asserted is that the number that exposes the loss is right, and that the 0.5 m row stays within 7.5 %.
    // Measured over these cells and five seeds: the fraction is off by at most 0.035 (0.15 m at ±5 mm, where the
    // segmenter's own range is inflated by the noise at its two ends); the 0.5 m row loses at most 3.65 %.
    for (const heightM of [0.15, 0.25, 0.5]) {
      for (const tempoS of [4, 8]) {
        for (const noiseM of [0.002, 0.005]) {
          for (const seed of seeds(5)) {
            const r = analyze(legSession({ legs: repLegs(2, heightM, tempoS, tempoS, 3), noiseM, seed }));
            expect(r.reps).toHaveLength(2);
            for (const rep of r.reps) {
              expect(Math.abs(rep.trimmedRangeFraction - rep.rangeOfMotionM / heightM)).toBeLessThan(0.06);
              if (heightM === 0.5) expect(relErr(rep.positiveWorkJ, MG * heightM)).toBeLessThan(0.075);
            }
          }
        }
      }
    }
  });
});

describe("constant-speed movement over 0.3 m: where the speed floor is", () => {
  /**
   * Up at a constant speed, 1 s at the top, down at the same speed, 3 s rests; the corners of the ramp are
   * rounded over 0.3 s. Unlike a minimum-jerk lift this has no fast middle, so it is the worst case.
   */
  function constantSpeed(speedMs: number, noiseM = 0, seed = 1): PoseFrame[] {
    const heightM = 0.3;
    const T = heightM / speedMs;
    const ramp = (t: number): number => (t <= 0 ? 0 : t >= T ? heightM : heightM * (t / T));
    const up = (t: number): number => {
      let sum = 0;
      for (let k = -15; k <= 15; k++) sum += ramp(t + k * 0.01);
      return sum / 31;
    };
    const position = (t: number): number => (t < 3 + T + 0.5 ? up(t - 3.2) : heightM - up(t - (3.2 + T + 1)));
    const noise = lcg(seed);
    const n = Math.round((3.2 + T + 1 + T + 3.5) * 60) + 1;
    return Array.from({ length: n }, (_, i) => ({ tS: i / 60, wristY: 0.7 - (position(i / 60) + noiseM * noise()) / SCALE, visibility: 1 }));
  }

  it("5, 8 and 12 cm/s: work and ROM within 3 %, no noise and ±2 mm over 10 seeds", () => {
    // measured: -1.3, -1.3 and -0.9 % with no noise; -1.5, -0.9 and -1.0 % worst at ±2 mm
    for (const speedMs of [0.05, 0.08, 0.12]) {
      for (const [noiseM, seedList] of [[0, [1]], [0.002, seeds(10)]] as const) {
        for (const seed of seedList) {
          const r = analyze(constantSpeed(speedMs, noiseM, seed));
          expect(r.reps).toHaveLength(1);
          const rep = r.reps[0]!;
          expect(relErr(rep.positiveWorkJ, MG * 0.3)).toBeLessThan(0.03);
          expect(relErr(-rep.negativeWorkJ, MG * 0.3)).toBeLessThan(0.03);
          expect(relErr(rep.rangeOfMotionM, 0.3)).toBeLessThan(0.03);
        }
      }
    }
  });

  it("3 cm/s with no noise is still measured (within 3.5 %): the floor is under it", () => {
    // measured -1.7 %. With ±2 mm of noise the same movement collapses (-60 to -66 %): see the README.
    const r = analyze(constantSpeed(0.03));
    expect(r.reps).toHaveLength(1);
    expect(relErr(r.reps[0]!.positiveWorkJ, MG * 0.3)).toBeLessThan(0.035);
    expect(r.reps[0]!.trimmedRangeFraction).toBeGreaterThan(0.965);
  });

  it("2 cm/s is under the floor: the rep collapses to the last 10 cm, and trimmedRangeFraction shows it", () => {
    // measured: work -67.7 %, trimmedRangeFraction 0.32. A pin of the limit the README states, not a goal.
    const r = analyze(constantSpeed(0.02));
    expect(r.reps).toHaveLength(1);
    const rep = r.reps[0]!;
    expect(rep.positiveWorkJ).toBeLessThan(MG * 0.3 * 0.5);
    expect(rep.trimmedRangeFraction).toBeLessThan(0.5);
    expect(rep.trimmedRangeFraction).toBeGreaterThan(0.25); // never less than the 10 cm under the top
  });
});
