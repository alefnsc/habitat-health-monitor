import { describe, expect, it } from "vitest";
import { G_ENV_MS2, trajectoryWork } from "@ground-truth/physics";
import { analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { legPosition, legSession, repLegs, syntheticSession, totalDurationS, type Leg } from "./helpers";

// Pins. Each test below is here because a specific wrong implementation survived the symmetric
// scenario the rest of the suite shares (0.5 m, 1 s up, 1 s down, 0.5 s rests). See the mutants named in each.

const SCALE = 2.5;
const MASS_KG = 10;
const EARTH = G_ENV_MS2.EARTH;
const MG = MASS_KG * EARTH; // 98.1 N

function analyze(frames: readonly PoseFrame[], over: Partial<Parameters<typeof analyzeSession>[1]> = {}): Extract<SessionResult, { ok: true }> {
  const r = analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE, ...over });
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

const percent = (actual: number, truth: number): number => ((actual - truth) / truth) * 100;

describe("the filter cutoff is pinned by a lift it cannot fully resolve", () => {
  // A 0.5 m lift in 0.4 s, no noise, 60 Hz. At the 4 Hz default the two-pass filter flattens it:
  // work reads about 8.2 % low and peak force 10.5 % low. At 6 Hz the same lift reads -2.9 % / -3.3 %,
  // at 8 Hz -2.2 % / -0.9 % (measured). A cutoff doubled or moved to 6 Hz inside analyzeSession changes both.
  // Truth: the same rep sampled at 2000 Hz, rest to rest, through trajectoryWork. (Not 49.05 J: at 0.4 s the
  // braking force m·a exceeds the weight, so part of the lift does negative work and W+ is 64.69 J.)
  const single: Leg[] = [[0.2, 0], [0.4, 0.5], [0.4, 0], [0.2, 0]];
  const hi = Array.from({ length: Math.round(totalDurationS(single) * 2000) + 1 }, (_, i) => ({ tS: i / 2000, yM: legPosition(single, i / 2000) }));
  const truth = trajectoryWork(hi, MASS_KG, EARTH);

  it("the truth for the 0.4 s rep is 64.69 J and 278.5 N", () => {
    expect(truth.positiveWorkJ).toBeCloseTo(64.69, 1);
    expect(truth.peakForceN).toBeCloseTo(MASS_KG * (EARTH + (5.7735 * 0.5) / 0.4 ** 2), 0);
  });

  it("at the default cutoff the middle rep reads work -8.2 % (±1 point) and peak force -10.5 % (±1 point)", () => {
    // Work was -5.92 % in the review, before the rep window was trimmed. Trimmed at the pause's edge (1.5 cm)
    // it read -9.69 %; trimmed at the rest level (3 mm) it reads -8.21 %. Peak force is unchanged.
    const rep = analyze(legSession({ legs: repLegs(3, 0.5, 0.4, 0.4, 1) })).reps[1]!;
    expect(percent(rep.positiveWorkJ, truth.positiveWorkJ)).toBeGreaterThan(-8.21 - 1);
    expect(percent(rep.positiveWorkJ, truth.positiveWorkJ)).toBeLessThan(-8.21 + 1);
    expect(percent(rep.peakForceN, truth.peakForceN)).toBeGreaterThan(-10.51 - 1);
    expect(percent(rep.peakForceN, truth.peakForceN)).toBeLessThan(-10.51 + 1);
  });

  it("a requested cutoff of 6 Hz and 8 Hz gives the values that distinguish them from the default", () => {
    const at = (cutoffHz: number) => analyze(legSession({ legs: repLegs(3, 0.5, 0.4, 0.4, 1) }), { cutoffHz }).reps[1]!;
    expect(percent(at(6).peakForceN, truth.peakForceN)).toBeGreaterThan(-3.34 - 1);
    expect(percent(at(6).peakForceN, truth.peakForceN)).toBeLessThan(-3.34 + 1);
    expect(percent(at(8).peakForceN, truth.peakForceN)).toBeGreaterThan(-0.86 - 1);
    expect(percent(at(8).peakForceN, truth.peakForceN)).toBeLessThan(-0.86 + 1);
  });
});

describe("startS is relative to the first frame of the recording", () => {
  it("a clock that starts at 123456.789 s gives the same startS as the same session starting at 0", () => {
    const frames = syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 60, noiseM: 0.002, seed: 1, metersPerUnit: SCALE });
    const shifted = frames.map((f) => ({ ...f, tS: f.tS + 123456.789 }));
    const a = analyze(frames);
    const b = analyze(shifted);
    expect(b.reps).toHaveLength(a.reps.length);
    a.reps.forEach((rep, k) => {
      expect(rep.startS).toBeLessThan(10);
      expect(b.reps[k]!.startS).toBeCloseTo(rep.startS, 6);
      expect(b.reps[k]!.positiveWorkJ).toBeCloseTo(rep.positiveWorkJ, 6);
    });
  });
});

describe("an asymmetric session: rep that rises 0.5 m and comes back only 0.35 m", () => {
  /**
   * 5 s rests; each rep rises 0.5 m and lowers to 0.15 m ABOVE where it started, and the next rep starts
   * from there (so the wrist climbs 0.15 m per rep, which is irrelevant to the physics: only differences count).
   */
  function asymmetric(upS: number, downS: number): PoseFrame[] {
    const legs: Leg[] = [[5, 0]];
    let base = 0;
    for (let k = 0; k < 3; k++) {
      legs.push([upS, base + 0.5], [downS, base + 0.15], [5, base + 0.15]);
      base += 0.15;
    }
    return legSession({ legs });
  }

  // Derivation for 0.6 s up, 1.4 s down (m = 10 kg, g = 9.81):
  //  - lift 0.5 m in 0.6 s: |m a|max = 10 × 5.7735 × 0.5 / 0.6² = 80.2 N < m g = 98.1 N, so the force is
  //    upward throughout and every interval of the lift is positive work: W+ = m g × 0.5 = 49.05 J
  //    (the kinetic energy borrowed while accelerating is given back while braking, inside the lift).
  //  - lowering 0.35 m in 1.4 s: |m a|max = 10.3 N, force upward throughout, motion downward: W- = -m g × 0.35 = -34.335 J.
  //  - peak force: m (g + a_max) at the lift's acceleration, 10 × (9.81 + 5.7735 × 0.5 / 0.36) = 178.3 N.
  //    The lowering peaks at only 10 × (9.81 + 5.7735 × 0.35 / 1.96) = 108.4 N.
  //  Measured with the window at the rest level: ROM 0.501, W+ 49.1 (+0.1 %), W- -34.2 (-0.4 %), peak 174.8 N
  //  (-2.0 %, the filter's share at 0.6 s). (At the pause's edge: ROM 0.489, W+ -3.6 %, W- -3.4 %.)
  it("0.6 s up, 1.4 s down: ROM is the lift height (0.5 m, not top - end = 0.35 m); positive and negative work are m g × 0.5 and -m g × 0.35", () => {
    const r = analyze(asymmetric(0.6, 1.4));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      // bounds are twice the measurement: ROM +0.22 %, W+ +0.10 %, W- -0.30 %, peak -1.99 %
      expect(Math.abs(percent(rep.rangeOfMotionM, 0.5))).toBeLessThan(0.5);
      expect(Math.abs(percent(rep.positiveWorkJ, MG * 0.5))).toBeLessThan(0.5);
      expect(Math.abs(percent(rep.negativeWorkJ, -MG * 0.35))).toBeLessThan(0.6);
      expect(rep.positiveWorkJ).toBeGreaterThan(-rep.negativeWorkJ * 1.3); // 49 vs 34: positive is not |negative|
      expect(Math.abs(percent(rep.peakForceN, 178.3))).toBeLessThan(4);
    }
  });

  // Derivation for 1.4 s up, 0.6 s down: the lift peaks at only 10 × (9.81 + 5.7735 × 0.5 / 1.96) = 112.8 N,
  // but the lowering of 0.35 m in 0.6 s brakes at a = 5.7735 × 0.35 / 0.36 = 5.61 m/s², so the force at the
  // end of the lowering is 10 × (9.81 + 5.61) = 154.2 N. The peak is in the LOWERING: a peak taken over the lift
  // alone would read 112.8 N. Measured 151.8 N (-1.6 %).
  it("1.4 s up, 0.6 s down: the peak force is in the lowering (154.2 N), not the lift (112.8 N)", () => {
    const r = analyze(asymmetric(1.4, 0.6));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      expect(Math.abs(percent(rep.peakForceN, 154.2))).toBeLessThan(3.2); // measured -1.58 %
      expect(rep.peakForceN).toBeGreaterThan(130);
      expect(Math.abs(percent(rep.rangeOfMotionM, 0.5))).toBeLessThan(0.55); // measured -0.26 %
    }
  });
});

describe("impulse", () => {
  it("of a rep that starts and ends near rest is m g × durationS within 2 %", () => {
    // impulse = (m g) Δt + m Δv. The window starts and ends at about 0.1 m/s (3 mm into the lift), so m Δv is
    // about -1.8 N·s against 180: 1 % low (2.9 % at the pause's edge, 1.5 cm in). A doubled impulse is 100 % high.
    const r = analyze(syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 5, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: SCALE }));
    for (const rep of r.reps) {
      expect(Math.abs(rep.impulseNs - MG * rep.durationS) / (MG * rep.durationS)).toBeLessThan(0.02); // measured 1.02 %
    }
  });
});
