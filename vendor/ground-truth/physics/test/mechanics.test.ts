import { describe, expect, it } from "vitest";
import { G_ENV_MS2, forceSeries, metabolicRange, trajectoryWork, type Sample } from "../src/index";

const MASS_KG = 10;
const HEIGHT_M = 0.5;
const DURATION_S = 1;

/** y = (h/2)(1 − cos(π t / T)) sampled at `hz` over [0, T]: a lift that starts and ends at rest. */
function cosineLift(heightM: number, durationS: number, hz: number): Sample[] {
  const n = Math.round(durationS * hz);
  const samples: Sample[] = [];
  for (let i = 0; i <= n; i++) {
    const tS = i / hz;
    samples.push({ tS, yM: (heightM / 2) * (1 - Math.cos((Math.PI * tS) / durationS)) });
  }
  return samples;
}

/** The lift followed by its mirror image (the lowering), sharing the top sample. */
function cosineRep(heightM: number, durationS: number, hz: number): Sample[] {
  const lift = cosineLift(heightM, durationS, hz);
  const lowering: Sample[] = [];
  for (let i = lift.length - 2; i >= 0; i--) {
    const s = lift[i]!;
    lowering.push({ tS: durationS + (lift.length - 1 - i) / hz, yM: s.yM });
  }
  return [...lift, ...lowering];
}

/**
 * The same lift sampled at deterministically jittered times: each interior
 * sample is shifted by 3 ms * sin(1.7 i) (a fixed formula, never Math.random).
 * The first and last samples keep their exact times so the lift still spans [0, T].
 */
function jitteredCosineLift(heightM: number, durationS: number, hz: number): Sample[] {
  const n = Math.round(durationS * hz);
  const samples: Sample[] = [];
  for (let i = 0; i <= n; i++) {
    const jitter = i === 0 || i === n ? 0 : 0.003 * Math.sin(1.7 * i);
    const tS = i / hz + jitter;
    samples.push({ tS, yM: (heightM / 2) * (1 - Math.cos((Math.PI * tS) / durationS)) });
  }
  return samples;
}

/** The first half of the lift, t in [0, T/2]: starts at rest, ends at the peak velocity. */
function cosineLiftFirstHalf(heightM: number, durationS: number, hz: number): Sample[] {
  return cosineLift(heightM, durationS, hz).slice(0, Math.round((durationS * hz) / 2) + 1);
}

/**
 * Constant acceleration for 0.7 s, then constant (harder) deceleration for 0.3 s, ending at rest,
 * sampled at 100 Hz so the switch falls on a sample. Piecewise quadratic, so the
 * three-point second derivative is exact on every sample whose neighbours lie in one segment.
 *   segment 1: a1 = +2 m/s² for 0.7 s    -> v1 = 1.4 m/s, y1 = 0.49 m
 *   segment 2: a2 = -v1 / 0.3 = -14/3 m/s² for 0.3 s -> rest at t = 1 s
 */
const ASYM_A1_MS2 = 2;
const ASYM_V1_MS = ASYM_A1_MS2 * 0.7;
const ASYM_A2_MS2 = -ASYM_V1_MS / 0.3;
function asymmetricStroke(): Sample[] {
  const hz = 100;
  const samples: Sample[] = [];
  for (let i = 0; i <= hz; i++) {
    const tS = i / hz;
    const yM =
      tS <= 0.7
        ? 0.5 * ASYM_A1_MS2 * tS * tS
        : 0.5 * ASYM_A1_MS2 * 0.49 + ASYM_V1_MS * (tS - 0.7) + 0.5 * ASYM_A2_MS2 * (tS - 0.7) ** 2;
    samples.push({ tS, yM });
  }
  return samples;
}

const earthWorkJ = MASS_KG * G_ENV_MS2.EARTH * HEIGHT_M; // 49.05
const withinRel = (actual: number, expected: number, rel: number) =>
  expect(Math.abs(actual - expected) / Math.abs(expected)).toBeLessThan(rel);

describe("trajectoryWork", () => {
  it("lift on Earth: all work is positive and equals m·g·h", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.positiveWorkJ, 49.05, 0.01);
    expect(Math.abs(r.negativeWorkJ)).toBeLessThan(0.5);
    withinRel(r.netWorkJ, 49.05, 0.01);
    expect(r.displacementM).toBeCloseTo(0.5, 6);
    expect(r.netWorkJ).toBeCloseTo(r.positiveWorkJ + r.negativeWorkJ, 9);
  });

  it("lift on Earth: peak force is m(g + a_max)", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    // 10 × (9.81 + 0.25 π²)
    withinRel(r.peakForceN, 122.77, 0.02);
  });

  it("first half of the lift (rest to moving): the inertial term adds energy, it does not subtract", () => {
    const samples = cosineLiftFirstHalf(HEIGHT_M, DURATION_S, 60);
    // Guard the test itself: it really is the half-lift, ending at the peak velocity.
    expect(samples[0]!.tS).toBe(0);
    expect(samples[samples.length - 1]!.tS).toBeCloseTo(0.5, 9);
    // Earth: m·g·(h/2) + ½ m v², v = (h/2)(π/T)  =  10·9.81·0.25 + 3.084
    const earth = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    withinRel(earth.netWorkJ, 27.609, 0.01);
    withinRel(earth.positiveWorkJ, 27.609, 0.01);
    expect(Math.abs(earth.negativeWorkJ)).toBeLessThan(0.05);
    // ISS: only the kinetic energy given to the mass, ½ m v² = 3.084 J, and nothing is returned yet.
    const iss = trajectoryWork(samples, MASS_KG, G_ENV_MS2.ISS);
    withinRel(iss.positiveWorkJ, 3.084, 0.03);
    expect(Math.abs(iss.negativeWorkJ)).toBeLessThan(0.05);
  });

  it("peak force on the ISS is m·a_max, with no gravity term", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.ISS);
    // 10 × 0.25 π²
    withinRel(r.peakForceN, 24.67, 0.01);
  });

  it("peak force can be the braking force: |F| is taken, and the sign of a matters on Earth", () => {
    // Deceleration (14/3 m/s²) is harder than acceleration (2 m/s²).
    // Analytic force on a 10 kg mass, F = m (g + a):
    //   g = 0 : accelerating  10 × 2     =  20.000 N
    //           braking       10 × -14/3 = -46.667 N   -> peak |F| = 46.667 N (a negative force)
    //   Earth : accelerating  10 × (9.81 + 2)     = 118.1 N
    //           braking       10 × (9.81 - 14/3)  =  51.43 N
    //           -> peak 118.1 N. Using g + |a| would give 10 × (9.81 + 14/3) = 144.77 N.
    // Samples 71..99 lie wholly in the braking segment, 1..69 in the accelerating one, so the
    // three-point acceleration is exact there and the peak is taken over interior samples.
    const samples = asymmetricStroke();
    const space = trajectoryWork(samples, MASS_KG, G_ENV_MS2.ISS);
    expect(space.peakForceN).toBeCloseTo(MASS_KG * Math.abs(ASYM_A2_MS2), 6); // 46.667
    expect(space.peakForceN).toBeGreaterThan(MASS_KG * ASYM_A1_MS2); // the braking force, not the accelerating one
    const earth = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    expect(earth.peakForceN).toBeCloseTo(MASS_KG * (G_ENV_MS2.EARTH + ASYM_A1_MS2), 6); // 118.1
  });

  it("lift then lower on Earth: the lowering gives the work back", () => {
    const r = trajectoryWork(cosineRep(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.positiveWorkJ, 49.05, 0.01);
    withinRel(r.negativeWorkJ, -49.05, 0.01);
    expect(Math.abs(r.netWorkJ)).toBeLessThan(0.5);
  });

  it("the same lift on the ISS: accelerating costs ½mv², stopping gives it back", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.ISS);
    // ½ · m · v_max², v_max = (h/2)(π/T)
    withinRel(r.positiveWorkJ, 3.084, 0.03);
    withinRel(r.negativeWorkJ, -3.084, 0.03);
    expect(Math.abs(r.netWorkJ)).toBeLessThan(0.1);
  });

  it("the same lift on the Moon: net work is m·g_moon·h", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.MOON);
    // 10 × 1.62 × 0.5
    withinRel(r.netWorkJ, 8.1, 0.01);
  });

  it("sampling at 30 Hz still gives the Earth lift within 1 %", () => {
    const samples = cosineLift(HEIGHT_M, DURATION_S, 30);
    const r = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.netWorkJ, earthWorkJ, 0.01);
    // net work depends only on the end samples; the split and the peak depend on every node velocity
    withinRel(r.peakForceN, 122.77, 0.02);
    const iss = trajectoryWork(samples, MASS_KG, G_ENV_MS2.ISS);
    withinRel(iss.positiveWorkJ, 3.084, 0.02);
    withinRel(iss.negativeWorkJ, -3.084, 0.02);
  });

  it("non-uniform time steps (deterministic jitter) stay within 2 %", () => {
    const samples = jitteredCosineLift(HEIGHT_M, DURATION_S, 60);
    // Guard the test itself: the time steps really are non-uniform.
    const steps = samples.slice(1).map((s, i) => s.tS - samples[i]!.tS);
    expect(Math.max(...steps) - Math.min(...steps)).toBeGreaterThan(0.004);
    const r = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.netWorkJ, earthWorkJ, 0.02);
    withinRel(r.peakForceN, 122.77, 0.02);
    const iss = trajectoryWork(samples, MASS_KG, G_ENV_MS2.ISS);
    withinRel(iss.positiveWorkJ, 3.084, 0.03);
    withinRel(iss.negativeWorkJ, -3.084, 0.03);
  });

  it("constant acceleration from rest is integrated exactly, on uniform and non-uniform time grids", () => {
    // y = ½ a t², a = 2 m/s², over [0, 1] s: the three-point velocity is exact for a quadratic,
    // so v_last = 2 m/s and the inertial work is ½ · 10 · 2² = 20 J with no discretisation error.
    // (A forward-difference velocity is off by a·h/2 at both ends and misses this by ~1.7 % at 60 Hz;
    // the cosine lifts cannot see that because their velocity is flat at the ends and the peak.)
    const a = 2;
    const quadratic = (times: number[]): Sample[] => times.map((tS) => ({ tS, yM: 0.5 * a * tS * tS }));
    const uniform = quadratic(Array.from({ length: 61 }, (_, i) => i / 60));
    const jittered = quadratic(Array.from({ length: 61 }, (_, i) => (i === 0 || i === 60 ? i / 60 : i / 60 + 0.003 * Math.sin(1.7 * i))));
    for (const samples of [uniform, jittered]) {
      const iss = trajectoryWork(samples, MASS_KG, G_ENV_MS2.ISS);
      expect(iss.positiveWorkJ).toBeCloseTo(20, 9);
      expect(iss.negativeWorkJ).toBeCloseTo(0, 9);
      // Earth adds m·g·Δy = 10 · 9.81 · 1
      expect(trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH).netWorkJ).toBeCloseTo(98.1 + 20, 9);
    }
  });

  describe("invalid input", () => {
    const ok = cosineLift(HEIGHT_M, DURATION_S, 60);

    it("rejects fewer than 3 samples", () => {
      expect(() => trajectoryWork(ok.slice(0, 2), MASS_KG, 9.81)).toThrow(RangeError);
      expect(() => trajectoryWork(ok.slice(0, 2), MASS_KG, 9.81)).toThrow(/samples/);
    });

    it("rejects non-increasing time", () => {
      const repeated = [{ tS: 0, yM: 0 }, { tS: 0.1, yM: 0.1 }, { tS: 0.1, yM: 0.2 }];
      const backwards = [{ tS: 0, yM: 0 }, { tS: 0.2, yM: 0.1 }, { tS: 0.1, yM: 0.2 }];
      expect(() => trajectoryWork(repeated, MASS_KG, 9.81)).toThrow(RangeError);
      expect(() => trajectoryWork(backwards, MASS_KG, 9.81)).toThrow(/tS/);
    });

    it("rejects negative mass", () => {
      expect(() => trajectoryWork(ok, -1, 9.81)).toThrow(RangeError);
      expect(() => trajectoryWork(ok, -1, 9.81)).toThrow(/massKg/);
    });

    it("rejects NaN in a sample", () => {
      const nanY = [{ tS: 0, yM: 0 }, { tS: 0.1, yM: Number.NaN }, { tS: 0.2, yM: 0.2 }];
      const nanT = [{ tS: 0, yM: 0 }, { tS: Number.NaN, yM: 0.1 }, { tS: 0.2, yM: 0.2 }];
      expect(() => trajectoryWork(nanY, MASS_KG, 9.81)).toThrow(RangeError);
      expect(() => trajectoryWork(nanY, MASS_KG, 9.81)).toThrow(/yM/);
      expect(() => trajectoryWork(nanT, MASS_KG, 9.81)).toThrow(RangeError);
    });

    it("rejects a non-finite gravity", () => {
      expect(() => trajectoryWork(ok, MASS_KG, Number.POSITIVE_INFINITY)).toThrow(/gEnvMs2/);
    });
  });
});

describe("trajectoryWork with a device force", () => {
  const DEVICE_N = 1000;
  const iss = { deviceForceN: DEVICE_N };

  it("lift at g = 0 with 1000 N: the device is the work, ½mv² is only a rounding on top", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.ISS, iss);
    // 1000 × 0.5 = 500 J; the kinetic term lifts and returns the same ½ m v² and never changes a sign.
    withinRel(r.positiveWorkJ, 500, 0.01);
    expect(Math.abs(r.negativeWorkJ)).toBeLessThan(0.5);
    // 1000 + 10 × 0.25 π²
    withinRel(r.peakForceN, 1024.67, 0.01);
  });

  it("lift then lower at g = 0 with 1000 N: the device does negative work on the way down", () => {
    const r = trajectoryWork(cosineRep(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.ISS, iss);
    withinRel(r.positiveWorkJ, 500, 0.01);
    withinRel(r.negativeWorkJ, -500, 0.01);
    expect(Math.abs(r.netWorkJ)).toBeLessThan(0.5);
  });

  it("an omitted option, an empty object and deviceForceN 0 all equal the old behaviour", () => {
    const samples = cosineRep(HEIGHT_M, DURATION_S, 60);
    const plain = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    for (const options of [{}, { deviceForceN: 0 }]) {
      const r = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH, options);
      expect(r.positiveWorkJ).toBe(plain.positiveWorkJ);
      expect(r.negativeWorkJ).toBe(plain.negativeWorkJ);
      expect(r.peakForceN).toBe(plain.peakForceN);
    }
  });

  it("the device force adds to the weight: Earth + 1000 N lifts 0.5 m for (98.1 + 1000) × 0.5 J net", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH, iss);
    withinRel(r.netWorkJ, (MASS_KG * G_ENV_MS2.EARTH + DEVICE_N) * HEIGHT_M, 0.005);
  });

  it("rejects a negative or non-finite device force", () => {
    const samples = cosineLift(HEIGHT_M, DURATION_S, 60);
    for (const bad of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => trajectoryWork(samples, MASS_KG, 9.81, { deviceForceN: bad })).toThrow(RangeError);
      expect(() => trajectoryWork(samples, MASS_KG, 9.81, { deviceForceN: bad })).toThrow(/deviceForceN/);
      expect(() => forceSeries(samples, MASS_KG, 9.81, { deviceForceN: bad })).toThrow(/deviceForceN/);
    }
  });
});

describe("trajectoryWork path length", () => {
  it("is 0.5 m for the lift and 1.0 m for lift then lower, where displacement is 0", () => {
    const lift = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    expect(lift.pathLengthM).toBeCloseTo(0.5, 9);
    const rep = trajectoryWork(cosineRep(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    expect(rep.pathLengthM).toBeCloseTo(1.0, 9);
    expect(rep.displacementM).toBeCloseTo(0, 9);
  });
});

describe("trajectoryWork impulse", () => {
  it("full lift on Earth: m·g·T plus the zero change in momentum, 98.1 N·s", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.impulseNs, 98.1, 0.005);
  });

  it("first half of the lift on Earth: weight over 0.5 s plus m·v_peak = 49.05 + 10 × 0.7854", () => {
    const r = trajectoryWork(cosineLiftFirstHalf(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.EARTH);
    withinRel(r.impulseNs, 56.904, 0.01);
  });

  it("full lift at g = 0 with 1000 N: F_device × T = 1000 N·s", () => {
    const r = trajectoryWork(cosineLift(HEIGHT_M, DURATION_S, 60), MASS_KG, G_ENV_MS2.ISS, { deviceForceN: 1000 });
    withinRel(r.impulseNs, 1000, 0.005);
  });

  it("uses the end velocities: a = 2 from rest for 1 s on Earth is m g T + m Δv", () => {
    // y = ½ a t², 1 s: Δv = 2 so m Δv = 20, weight impulse 98.1  ->  118.1 N·s, exact for a quadratic.
    const samples = Array.from({ length: 61 }, (_, i) => ({ tS: i / 60, yM: (i / 60) ** 2 }));
    const r = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH);
    expect(r.impulseNs).toBeCloseTo(118.1, 9);
  });
});

describe("forceSeries", () => {
  // y = ½ a t² with a = 2 m/s²: the three-point acceleration is exact, so every force is m (g + a).
  const quadratic = Array.from({ length: 61 }, (_, i) => ({ tS: i / 60, yM: (i / 60) ** 2 }));

  it("returns the interior samples only, each at its own time, with force 118.1 N on Earth", () => {
    const series = forceSeries(quadratic, MASS_KG, G_ENV_MS2.EARTH);
    expect(series).toHaveLength(quadratic.length - 2);
    expect(series[0]!.tS).toBeCloseTo(1 / 60, 12);
    expect(series[series.length - 1]!.tS).toBeCloseTo(59 / 60, 12);
    for (const p of series) expect(p.forceN).toBeCloseTo(118.1, 9);
  });

  it("is signed (a braking force on the ISS is negative) and includes the device force", () => {
    const decel = Array.from({ length: 61 }, (_, i) => ({ tS: i / 60, yM: -((i / 60) ** 2) }));
    for (const p of forceSeries(decel, MASS_KG, G_ENV_MS2.ISS)) expect(p.forceN).toBeCloseTo(-20, 9);
    for (const p of forceSeries(quadratic, MASS_KG, G_ENV_MS2.EARTH, { deviceForceN: 50 })) expect(p.forceN).toBeCloseTo(168.1, 9);
  });

  it("agrees with the peak force trajectoryWork reports", () => {
    const samples = cosineRep(HEIGHT_M, DURATION_S, 60);
    const series = forceSeries(samples, MASS_KG, G_ENV_MS2.EARTH, { deviceForceN: 30 });
    const peak = trajectoryWork(samples, MASS_KG, G_ENV_MS2.EARTH, { deviceForceN: 30 }).peakForceN;
    expect(Math.max(...series.map((p) => Math.abs(p.forceN)))).toBe(peak);
  });

  it("validates the samples like trajectoryWork", () => {
    expect(() => forceSeries(quadratic.slice(0, 2), MASS_KG, 9.81)).toThrow(/samples/);
  });
});

describe("metabolicRange", () => {
  it("returns a labelled range from gross efficiency 0.20–0.25", () => {
    const r = metabolicRange(49.05);
    expect(r.lowJ).toBeCloseTo(196.2, 6);
    expect(r.highJ).toBeCloseTo(245.25, 6);
    expect(r.kind).toBe("ESTIMATE");
    expect(r.basis).toContain("0.20");
    expect(r.basis).toContain("0.25");
  });

  it("rejects negative or non-finite work", () => {
    expect(() => metabolicRange(-1)).toThrow(RangeError);
    expect(() => metabolicRange(-1)).toThrow(/positiveWorkJ/);
    expect(() => metabolicRange(Number.NaN)).toThrow(RangeError);
  });
});
