import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import {
  FILTER_LIMITED_LIFT_S,
  VALIDATED_ON_REAL_VIDEO,
  analyzeSession,
  assessQuality,
  gradeCaptureConditions,
  type PoseFrame,
  type SessionResult,
} from "../src/index";
import { lcg, legSession, repLegs, syntheticSession } from "./helpers";

const SCALE = 2.5; // metres per image unit used to synthesise the frames
const MASS_KG = 10;
const HEIGHT_M = 0.5;
const EARTH = G_ENV_MS2.EARTH;

// Truth for one rep of 10 kg lifted 0.5 m in 1 s (minimum jerk) and lowered in 1 s, on Earth.
const TRUE_WORK_J = MASS_KG * EARTH * HEIGHT_M; // 49.05: the kinetic energy is borrowed and returned inside the lift
const TRUE_PEAK_N = MASS_KG * (EARTH + (5.7735 * HEIGHT_M) / 1 ** 2); // 126.97: max |a| of min-jerk is 5.7735·h/T²
const TRUE_ROM_M = HEIGHT_M;

function session(over: Partial<Parameters<typeof syntheticSession>[0]> = {}): PoseFrame[] {
  return syntheticSession({ reps: 3, heightM: HEIGHT_M, upS: 1, downS: 1, restS: 0.5, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: SCALE, ...over });
}

function analyze(frames: readonly PoseFrame[], over: Partial<Parameters<typeof analyzeSession>[1]> = {}): SessionResult {
  return analyzeSession(frames, { massKg: MASS_KG, gEnvMs2: EARTH, metersPerUnit: SCALE, ...over });
}

function ok(r: SessionResult) {
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

const relErr = (actual: number, expected: number): number => Math.abs(actual - expected) / Math.abs(expected);
const worst = (xs: readonly number[]): number => Math.max(...xs);

/** Every low-visibility frame carries garbage in wristY: if it leaks into the result the numbers explode. */
function loseFrames(frames: PoseFrame[], every: number, offset = 3): PoseFrame[] {
  return frames.map((f, i) => (i % every === offset ? { ...f, visibility: 0.2, wristY: 999 } : f));
}

describe("analyzeSession: measurement", () => {
  it("3 reps, 60 Hz, no noise: work within 2 %, peak within 3 %, range of motion within 1 %", () => {
    // The plan's targets. The rep window is trimmed to the rest level (ONSET_TOLERANCE_M = 3 mm at each end),
    // which reads a 0.5 m rep 0.5 % short in work and 0.4 % in range of motion (see README). While the
    // boundary sat at the pause's edge (1.5 cm) these were 3.2 % and 2.6 %, and the bounds were 4 % and 3 %.
    const r = ok(analyze(session()));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.02);
      expect(relErr(rep.peakForceN, TRUE_PEAK_N)).toBeLessThan(0.03);
      expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.01);
      // the lowering gives the work back
      expect(relErr(-rep.negativeWorkJ, TRUE_WORK_J)).toBeLessThan(0.02);
    }
    // a clean 60 Hz stream grades HIGH on capture conditions, but nothing has been checked on real video: capped
    expect(r.provenance).toEqual({ loadSource: "CAMERA", confidence: "MEDIUM" });
  });

  it("reports when each rep started and how long it took, and the session totals", () => {
    const r = ok(analyze(session()));
    // rep k lifts from t = 0.5 + 2.5 k and is back at the bottom at 2.5 + 2.5 k: the window is the movement,
    // 2 s less the 3 mm at each end that count as rest (measured: starts 0.08 s late, 1.83 s long)
    r.reps.forEach((rep, k) => {
      expect(rep.durationS).toBeGreaterThan(1.75);
      expect(rep.durationS).toBeLessThan(2.1);
      expect(rep.startS).toBeGreaterThan(0.5 + 2.5 * k - 0.1);
      expect(rep.startS).toBeLessThan(0.5 + 2.5 * k + 0.15);
      expect(rep.liftDurationS).toBeGreaterThan(0.7);
      expect(rep.liftDurationS).toBeLessThan(1.05);
      expect(rep.impulseNs).toBeGreaterThan(0);
    });
    expect(r.totalPositiveWorkJ).toBeCloseTo(r.reps.reduce((s, x) => s + x.positiveWorkJ, 0), 9);
    expect(r.maxPeakForceN).toBe(Math.max(...r.reps.map((x) => x.peakForceN)));
    expect(r.quality.reasons).toEqual([]);
  });

  it("3 reps, 60 Hz, ±2 mm noise: work within 5 %, peak within 10 %, range of motion within 3 %, confidence MEDIUM (capped)", () => {
    const r = ok(analyze(session({ noiseM: 0.002 })));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.05);
      expect(relErr(rep.peakForceN, TRUE_PEAK_N)).toBeLessThan(0.1);
      expect(relErr(rep.rangeOfMotionM, TRUE_ROM_M)).toBeLessThan(0.03);
    }
    expect(r.provenance.confidence).toBe("MEDIUM");
  });

  it("3 reps, 30 Hz, ±2 mm noise: work within 5 %, confidence MEDIUM", () => {
    const r = ok(analyze(session({ noiseM: 0.002, rateHz: 30 })));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.05);
    expect(r.provenance.confidence).toBe("MEDIUM");
  });

  it("3 reps, 60 Hz, ±5 mm noise: work within 10 % (peak force is reported by the README, not asserted)", () => {
    const r = ok(analyze(session({ noiseM: 0.005 })));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.1);
  });

  it("3 reps, 60 Hz, ±2 mm, 4 % of frames low-visibility at fixed indices: work within 8 %, confidence MEDIUM", () => {
    const frames = loseFrames(session({ noiseM: 0.002 }), 25);
    const lost = frames.filter((f) => f.visibility < 0.5).length / frames.length;
    expect(lost).toBeGreaterThan(0.035);
    expect(lost).toBeLessThan(0.045);
    const r = ok(analyze(frames));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.08);
    expect(r.provenance.confidence).toBe("MEDIUM");
  });

  it("5 reps with three different seeds: 5 reps every time", () => {
    for (const seed of [3, 17, 99]) {
      const r = ok(analyze(session({ reps: 5, noiseM: 0.002, seed })));
      expect(r.reps).toHaveLength(5);
    }
  });

  it("ISS, deviceForceN 1000, 3 reps, ±2 mm: positive work per rep within 5 % of 500 J", () => {
    // Derivation. At g = 0 the force on the load is F = m a + F_device, with F_device = 1000 N.
    // Work over the lift = ∫ F dy = F_device · h + ½ m (v_end² − v_start²) = 1000 × 0.5 + 0 = 500 J,
    // because the lift starts and ends at rest.
    // The kinetic term: a minimum-jerk lift peaks at v_max = 1.875 h/T = 0.9375 m/s, so the
    // kinetic energy it borrows while accelerating is ½ m v_max² = ½ × 10 × 0.9375² = 4.395 J.
    // It is given back while braking inside the same lift, and no interval changes sign
    // (|m a|max = 10 × 5.7735 × 0.5 = 28.9 N, against 1000 N), so every lift interval counts
    // as positive work and the borrowed 4.395 J cancels: the kinetic part of the positive work is 0.
    // The lowering is the mirror image, 1000 N × (−0.5 m) = −500 J of negative work, with no positive part.
    // Expected positive work per rep: 500 J (plus 0 J kinetic). Device force dominates the signal here,
    // so position noise is multiplied by 1000 N rather than 98.1 N in the rectified sum, hence the test is
    // the harder one for the filter.
    const r = ok(analyze(session({ noiseM: 0.002 }), { gEnvMs2: G_ENV_MS2.ISS, deviceForceN: 1000 }));
    expect(r.reps).toHaveLength(3);
    for (const rep of r.reps) {
      expect(relErr(rep.positiveWorkJ, 1000 * HEIGHT_M)).toBeLessThan(0.05);
      expect(relErr(-rep.negativeWorkJ, 1000 * HEIGHT_M)).toBeLessThan(0.05);
    }
  });

  it("the same ISS session without the device force measures only the kinetic exchange: 2 × ½ m v_max² = 8.79 J", () => {
    // Free fall: accelerating the mass costs ½ m v_max² = 4.395 J (v_max = 1.875 h/T = 0.9375 m/s) and braking
    // returns it as negative work. That happens twice per rep, once going up and once coming down.
    const r = ok(analyze(session(), { gEnvMs2: G_ENV_MS2.ISS }));
    for (const rep of r.reps) {
      // measured 0.8 % low: the window starts and ends at about 0.1 m/s, 3 mm into the lift, so a sliver of the
      // kinetic exchange belongs to the rest (3.7 % low while the boundary sat at the pause's edge, 1.5 cm in)
      expect(relErr(rep.positiveWorkJ, 2 * 0.5 * MASS_KG * 0.9375 ** 2)).toBeLessThan(0.03);
      expect(relErr(-rep.negativeWorkJ, 2 * 0.5 * MASS_KG * 0.9375 ** 2)).toBeLessThan(0.03);
    }
  });

  it("a scale 3 % too large makes the work 3 % too large (within 0.5 points): scale error passes straight through", () => {
    const frames = session();
    const right = ok(analyze(frames, { metersPerUnit: SCALE }));
    const wrong = ok(analyze(frames, { metersPerUnit: SCALE * 1.03 }));
    expect(wrong.reps).toHaveLength(3);
    wrong.reps.forEach((rep, k) => {
      const ratio = rep.positiveWorkJ / (right.reps[k] as { positiveWorkJ: number }).positiveWorkJ;
      expect(Math.abs(ratio - 1.03)).toBeLessThan(0.005);
      expect(Math.abs(rep.rangeOfMotionM / (right.reps[k] as { rangeOfMotionM: number }).rangeOfMotionM - 1.03)).toBeLessThan(0.005);
      // and against the truth, the error is the scale error and not much else (measured +2.5 %: the +3 % less the
      // 0.5 % the trimmed window leaves out). It was cancelled almost exactly while the window lost 3.2 %.
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeGreaterThan(0.02);
      expect(relErr(rep.positiveWorkJ, TRUE_WORK_J)).toBeLessThan(0.04);
    });
  });
});

describe("analyzeSession: path length", () => {
  it("pathLengthM is the distance travelled inside the rep window: up and down, twice the range of motion for a rep that returns", () => {
    const r = ok(analyze(session()));
    for (const rep of r.reps) {
      // measured 0.9963: 3 mm at each of the two ends count as rest (bound: twice the 0.37 % measured)
      expect(relErr(rep.pathLengthM, 2 * HEIGHT_M)).toBeLessThan(0.0075);
      expect(relErr(rep.pathLengthM, 2 * rep.rangeOfMotionM)).toBeLessThan(0.001);
    }
  });

  it("pathLengthM of a rep that rises 0.5 m and comes back 0.35 m is 0.85 m, not twice the range of motion", () => {
    const frames = legSession({ legs: [[3, 0], [1, 0.5], [1, 0.15], [3, 0.15]] });
    const r = ok(analyze(frames));
    expect(r.reps).toHaveLength(1);
    expect(relErr(r.reps[0]!.pathLengthM, 0.85)).toBeLessThan(0.01); // measured 0.8455 (-0.5 %)
    expect(relErr(r.reps[0]!.rangeOfMotionM, 0.5)).toBeLessThan(0.01);
  });
});

describe("analyzeSession: refusal", () => {
  it("metersPerUnit null: refused with NO_SCALE and no measurement fields", () => {
    const r = analyze(session({ noiseM: 0.002 }), { metersPerUnit: null });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toContain("NO_SCALE");
    expect(r.quality.reasons).toEqual(r.reasons);
    for (const key of ["reps", "totalPositiveWorkJ", "maxPeakForceN", "provenance"]) expect(key in r).toBe(false);
  });

  it("15 Hz: refused with LOW_FRAME_RATE", () => {
    const r = analyze(session({ rateHz: 15 }));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["LOW_FRAME_RATE"]);
  });

  it("a lost landmark for 0.5 s is refused with GAP_TOO_LONG, whatever the rest of the session looks like", () => {
    const frames = session({ noiseM: 0.002 }).map((f, i) => (i >= 100 && i < 130 ? { ...f, visibility: 0.1, wristY: 999 } : f));
    const r = analyze(frames);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["GAP_TOO_LONG"]);
  });

  it("several reasons at once are all reported", () => {
    const r = analyze(session({ rateHz: 15 }), { metersPerUnit: null });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["NO_SCALE", "LOW_FRAME_RATE"]);
  });

  it("a stationary noisy 6 s recording: refused with NO_REPS, not measured as 0 J", () => {
    const r = analyze(session({ reps: 0, restS: 6, noiseM: 0.002 }));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["NO_REPS"]);
    expect(r.quality.reasons).toEqual(["NO_REPS"]);
    for (const key of ["reps", "totalPositiveWorkJ", "maxPeakForceN", "provenance"]) expect(key in r).toBe(false);
  });

  it("a lift that is never lowered is refused with NO_REPS, and keeps its quality diagnostics", () => {
    const r = analyze(legSession({ legs: [[1, 0], [1, 0.5], [2, 0.5]], noiseM: 0.002 }));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["NO_REPS"]);
    expect(r.quality.rateHz).toBeCloseTo(60, 6);
    expect(r.quality.durationS).toBeCloseTo(4, 6);
  });

  it("one complete repetition is enough: lifted and lowered once is a measurement", () => {
    expect(ok(analyze(session({ reps: 1, noiseM: 0.002 }))).reps).toHaveLength(1);
  });
});

describe("analyzeSession: confidence", () => {
  // Capture-conditions grade, before the cap: LOW below 27 Hz or above 5 % lost frames, HIGH from 45 Hz with at most 2 %.
  const grade = (frames: readonly PoseFrame[]) => gradeCaptureConditions(ok(analyze(frames)).quality);
  const reported = (frames: readonly PoseFrame[]) => ok(analyze(frames)).provenance.confidence;

  it("is LOW below 27 Hz and above 5 % low-visibility frames, MEDIUM from 27 Hz, HIGH from 45 Hz with at most 2 %", () => {
    const base = (rateHz: number) => session({ noiseM: 0.002, rateHz });
    expect(grade(base(25))).toBe("LOW");
    expect(grade(base(30))).toBe("MEDIUM");
    expect(grade(base(50))).toBe("HIGH");
    expect(grade(base(60))).toBe("HIGH");
    // 1.7 % lost is still HIGH, 3.1 % is MEDIUM, 6.2 % is LOW (481 frames)
    expect(grade(loseFrames(base(60), 60))).toBe("HIGH");
    expect(grade(loseFrames(base(60), 33))).toBe("MEDIUM");
    expect(grade(loseFrames(base(60), 16))).toBe("LOW");
  });

  it("the reported grade is that grade capped at MEDIUM while nothing is validated on real video", () => {
    expect(VALIDATED_ON_REAL_VIDEO).toBe(false);
    const base = (rateHz: number) => session({ noiseM: 0.002, rateHz });
    expect(reported(base(25))).toBe("LOW");
    expect(reported(base(30))).toBe("MEDIUM");
    expect(reported(base(60))).toBe("MEDIUM"); // HIGH on capture conditions, capped
    expect(reported(loseFrames(base(60), 60))).toBe("MEDIUM");
    expect(reported(loseFrames(base(60), 16))).toBe("LOW");
  });

  it("the uncapped grading function still returns HIGH for a clean 60 Hz stream", () => {
    expect(gradeCaptureConditions(assessQuality(session({ noiseM: 0.002 }), true))).toBe("HIGH");
    expect(gradeCaptureConditions({ rateHz: 60, lowVisibilityFraction: 0 })).toBe("HIGH");
    expect(gradeCaptureConditions({ rateHz: 60, lowVisibilityFraction: 0.03 })).toBe("MEDIUM");
  });

  it("the nominal camera rates sit inside their grade, not on its edge: 29.97 and 30.3 grade alike, 59.94 and 50 grade alike", () => {
    const at = (rateHz: number) => session({ noiseM: 0.002, rateHz });
    expect(grade(at(29.97))).toBe(grade(at(30.3)));
    expect(grade(at(29.97))).toBe("MEDIUM");
    expect(grade(at(59.94))).toBe(grade(at(50)));
    expect(grade(at(59.94))).toBe("HIGH");
    expect(reported(at(29.97))).toBe(reported(at(30.3)));
    expect(reported(at(59.94))).toBe(reported(at(50)));
  });

  it("23.976 fps is accepted and 15 fps is refused", () => {
    expect(reported(session({ noiseM: 0.002, rateHz: 23.976 }))).toBe("LOW");
    const r = analyze(session({ rateHz: 15 }));
    expect(r.ok).toBe(false);
  });
});

describe("analyzeSession: filterLimited", () => {
  it("is true for a 0.4 s lift, which the 4 Hz default cutoff cannot resolve, and false for a 1.0 s lift", () => {
    expect(FILTER_LIMITED_LIFT_S).toBe(0.65);
    const fast = ok(analyze(legSession({ legs: repLegs(3, 0.5, 0.4, 0.4, 1) })));
    expect(fast.reps).toHaveLength(3);
    for (const rep of fast.reps) {
      expect(rep.liftDurationS).toBeLessThan(FILTER_LIMITED_LIFT_S);
      expect(rep.filterLimited).toBe(true);
    }
    const slow = ok(analyze(session()));
    for (const rep of slow.reps) {
      expect(rep.liftDurationS).toBeGreaterThanOrEqual(FILTER_LIMITED_LIFT_S);
      expect(rep.filterLimited).toBe(false);
    }
  });
});

describe("analyzeSession: overridable quality limits", () => {
  const murky = (): PoseFrame[] => {
    const noise = lcg(5);
    return session({ noiseM: 0.002 }).map((f) => ({ ...f, visibility: 0.55 + 0.1 * noise() })); // uniform 0.45 .. 0.65
  };

  it("a session refused with the default visibility threshold (0.5) is accepted with visibilityThreshold 0.4", () => {
    const refused = analyze(murky());
    expect(refused.ok).toBe(false);
    if (refused.ok) return;
    expect(refused.reasons).toContain("LANDMARK_LOST");
    const accepted = ok(analyze(murky(), { visibilityThreshold: 0.4 }));
    expect(accepted.reps).toHaveLength(3);
    expect(accepted.quality.lowVisibilityFraction).toBe(0);
  });

  it("a 0.4 s lost run is refused by default and accepted with maxGapS 0.5", () => {
    const frames = session({ noiseM: 0.002 }).map((f, i) => (i >= 100 && i < 124 ? { ...f, visibility: 0.1, wristY: 999 } : f));
    const refused = analyze(frames);
    expect(refused.ok).toBe(false);
    if (refused.ok) return;
    expect(refused.reasons).toEqual(["GAP_TOO_LONG"]);
    expect(ok(analyze(frames, { maxGapS: 0.5 })).reps).toHaveLength(3);
  });

  it("rejects an out-of-range visibilityThreshold or a non-positive maxGapS with a RangeError naming it", () => {
    const f = session();
    expect(() => analyze(f, { visibilityThreshold: 1.5 })).toThrow(/visibilityThreshold/);
    expect(() => analyze(f, { visibilityThreshold: Number.NaN })).toThrow(/visibilityThreshold/);
    expect(() => analyze(f, { maxGapS: 0 })).toThrow(/maxGapS/);
  });
});

describe("analyzeSession: invalid input", () => {
  it("rejects an invalid mass, gravity, device force, cutoff, threshold or scale with a RangeError naming it", () => {
    const f = session();
    expect(() => analyze(f, { massKg: -1 })).toThrow(/massKg/);
    expect(() => analyze(f, { gEnvMs2: Number.NaN })).toThrow(/gEnvMs2/);
    expect(() => analyze(f, { deviceForceN: -5 })).toThrow(/deviceForceN/);
    expect(() => analyze(f, { cutoffHz: -4 })).toThrow(/cutoffHz/);
    expect(() => analyze(f, { cutoffHz: Number.POSITIVE_INFINITY })).toThrow(/cutoffHz/);
    expect(() => analyze(f, { minPhaseDisplacementM: 0 })).toThrow(/minPhaseDisplacementM/);
    expect(() => analyze(f, { metersPerUnit: 0 })).toThrow(/metersPerUnit/);
    expect(() => analyze(f, { metersPerUnit: Number.NaN })).toThrow(RangeError);
  });

  it("a cutoff above this stream's Nyquist frequency (40 Hz at 60 fps) is a refusal, not an exception", () => {
    const r = analyze(session(), { cutoffHz: 40 });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["LOW_FRAME_RATE"]);
  });

  it("honours cutoffHz and minPhaseDisplacementM", () => {
    const f = session({ noiseM: 0.002 });
    const defaults = ok(analyze(f));
    const wide = ok(analyze(f, { cutoffHz: 10 }));
    expect(wide.maxPeakForceN).toBeGreaterThan(defaults.maxPeakForceN);
    const none = analyze(f, { minPhaseDisplacementM: 0.6 });
    expect(none.ok).toBe(false);
    if (!none.ok) expect(none.reasons).toEqual(["NO_REPS"]);
  });
});
