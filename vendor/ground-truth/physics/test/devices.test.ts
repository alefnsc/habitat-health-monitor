import { describe, expect, it } from "vitest";
import {
  ARED_FLYWHEEL_EFFECTIVE_MASS_KG,
  aredPeakForceN,
  aredRepWorkJ,
  deviceForceForEarthEquivalenceN,
  ergometerActualPowerW,
  ergometerWorkJ,
  froudeTransitionSpeedMs,
  totalForceN,
  treadmillEffectiveForceN,
} from "../src/index";

describe("cycle ergometer", () => {
  it("applies the dynamometer correction 0.98·P − 11.8", () => {
    expect(ergometerActualPowerW(75)).toBeCloseTo(61.7, 6);
  });

  it("floors delivered power at zero", () => {
    expect(ergometerActualPowerW(10)).toBe(0);
  });

  it("integrates delivered power over 45 minutes at a constant 150 W displayed", () => {
    const work = ergometerWorkJ([
      { tS: 0, displayedPowerW: 150 },
      { tS: 2700, displayedPowerW: 150 },
    ]);
    // actual 135.2 W × 2700 s
    expect(work).toBeCloseTo(365040, 3);
  });

  it("integrates by the trapezoid rule over uneven steps", () => {
    const work = ergometerWorkJ([
      { tS: 0, displayedPowerW: 100 },
      { tS: 10, displayedPowerW: 200 },
      { tS: 30, displayedPowerW: 200 },
    ]);
    // actual 86.2 → 184.2 → 184.2 W: 10·(86.2+184.2)/2 + 20·184.2
    expect(work).toBeCloseTo(1352 + 3684, 6);
  });

  it("applies the zero floor to each sample before integrating (a 0 W display at rest)", () => {
    const work = ergometerWorkJ([
      { tS: 0, displayedPowerW: 100 },
      { tS: 10, displayedPowerW: 0 },
      { tS: 20, displayedPowerW: 100 },
    ]);
    // actual 86.2 W, floored 0 W (not -11.8), 86.2 W:
    //   10·(86.2 + 0)/2 + 10·(0 + 86.2)/2 = 862 J
    // Integrating the unfloored power would give 10·(86.2 − 11.8)/2 × 2 = 744 J.
    expect(work).toBeCloseTo(862, 6);
  });

  it("rejects fewer than 2 samples, non-increasing time and non-finite power", () => {
    expect(() => ergometerWorkJ([{ tS: 0, displayedPowerW: 100 }])).toThrow(RangeError);
    expect(() =>
      ergometerWorkJ([
        { tS: 5, displayedPowerW: 100 },
        { tS: 5, displayedPowerW: 100 },
      ]),
    ).toThrow(/tS/);
    expect(() =>
      ergometerWorkJ([
        { tS: 0, displayedPowerW: Number.NaN },
        { tS: 5, displayedPowerW: 100 },
      ]),
    ).toThrow(/displayedPowerW/);
    expect(() => ergometerActualPowerW(Number.POSITIVE_INFINITY)).toThrow(RangeError);
  });
});

describe("body-weight replacement", () => {
  it("adds m·g_env to the device force", () => {
    expect(totalForceN(1000, 78.4, 9.81)).toBeCloseTo(1769.1, 1);
    expect(totalForceN(1000, 78.4, 0)).toBe(1000);
  });

  it("subtracts m·g_env from the target to get the device setting", () => {
    expect(deviceForceForEarthEquivalenceN(1769.104, 78.4, 0)).toBeCloseTo(1769.1, 1);
    expect(deviceForceForEarthEquivalenceN(1769.104, 78.4, 9.81)).toBeCloseTo(1000, 3);
  });

  it("rejects negative mass and non-finite arguments", () => {
    expect(() => totalForceN(1000, -1, 9.81)).toThrow(/massKg/);
    expect(() => totalForceN(Number.NaN, 78.4, 9.81)).toThrow(/deviceForceN/);
    expect(() => totalForceN(1000, 78.4, Number.POSITIVE_INFINITY)).toThrow(/gEnvMs2/);
    expect(() => deviceForceForEarthEquivalenceN(1769, -1, 0)).toThrow(/massKg/);
    expect(() => deviceForceForEarthEquivalenceN(Number.NaN, 78.4, 0)).toThrow(/targetForceN/);
  });
});

describe("treadmill with subject load device", () => {
  it("is the harness force alone in microgravity", () => {
    // 0.7 × 78.4 × 9.81
    expect(treadmillEffectiveForceN(78.4, 0, 0.7)).toBeCloseTo(538.37, 2);
  });

  it("is body weight alone on Earth with no harness", () => {
    expect(treadmillEffectiveForceN(78.4, 9.81, 0)).toBeCloseTo(769.1, 1);
  });

  it("adds the harness to body weight at partial gravity", () => {
    // Mars, half a body weight of harness: 78.4 × 3.71 + 0.5 × 78.4 × 9.81 = 290.864 + 384.552
    expect(treadmillEffectiveForceN(78.4, 3.71, 0.5)).toBeCloseTo(675.416, 3);
  });

  it("rejects negative mass, non-finite arguments and a support fraction outside [0, 1]", () => {
    expect(() => treadmillEffectiveForceN(-1, 0, 0.5)).toThrow(/massKg/);
    expect(() => treadmillEffectiveForceN(78.4, Number.NaN, 0.5)).toThrow(RangeError);
    expect(() => treadmillEffectiveForceN(78.4, 0, 1.01)).toThrow(/supportFraction/);
    expect(() => treadmillEffectiveForceN(78.4, 0, -0.01)).toThrow(/supportFraction/);
  });
});

describe("ARED", () => {
  it("concentric work is setting × stroke, eccentric is 0.9 of it by default", () => {
    const w = aredRepWorkJ(2669, 0.762);
    expect(w.concentricJ).toBeCloseTo(2033.78, 2);
    expect(w.eccentricMagnitudeJ).toBeCloseTo(1830.4, 2);
  });

  it("honours an explicit eccentric ratio", () => {
    expect(aredRepWorkJ(2000, 0.5, 0.5)).toEqual({ concentricJ: 1000, eccentricMagnitudeJ: 500 });
  });

  it("rejects an eccentric ratio outside [0, 0.9]", () => {
    expect(() => aredRepWorkJ(2669, 0.762, 0.95)).toThrow(RangeError);
    expect(() => aredRepWorkJ(2669, 0.762, 0.95)).toThrow(/eccentricRatio/);
    expect(() => aredRepWorkJ(2669, 0.762, -0.1)).toThrow(RangeError);
  });

  it("reproduces the brief's +893 N flywheel anchor (calibrated effective mass)", () => {
    expect(ARED_FLYWHEEL_EFFECTIVE_MASS_KG).toBeCloseTo(237.5, 1);
    expect(aredPeakForceN(2669, 0.762, 2)).toBeCloseTo(3562, 0);
    expect(Math.abs(aredPeakForceN(2669, 0.762, 2) - 3562)).toBeLessThan(1);
  });

  it("halves the inertial term when the stroke halves", () => {
    // inertial 893 / 2 = 446.5 N on top of the 2669 N setting
    expect(aredPeakForceN(2669, 0.381, 2)).toBeCloseTo(3115.5, 6);
  });

  it("adds the same inertial term at a different setting (the model assumes M_eff does not depend on the load)", () => {
    // 1334.5 N (300 lbf) + the 893 N anchor term: documents the assumption as a tested property
    expect(aredPeakForceN(1334.5, 0.762, 2)).toBeCloseTo(2227.5, 6);
  });

  it("quarters the inertial term when the rep period doubles", () => {
    expect(aredPeakForceN(2669, 0.762, 4)).toBeCloseTo(2892.25, 1);
  });

  it("rejects negative settings and a non-positive rep period", () => {
    expect(() => aredPeakForceN(-1, 0.762, 2)).toThrow(/settingN/);
    expect(() => aredPeakForceN(2669, 0.762, 0)).toThrow(/repPeriodS/);
    expect(() => aredRepWorkJ(2669, Number.NaN)).toThrow(/strokeM/);
  });
});

describe("Froude walk-run transition", () => {
  it("falls with gravity", () => {
    expect(froudeTransitionSpeedMs(9.81, 0.9)).toBeCloseTo(2.101, 3);
    expect(froudeTransitionSpeedMs(1.62, 0.9)).toBeCloseTo(0.854, 3);
    expect(froudeTransitionSpeedMs(3.71, 0.9)).toBeCloseTo(1.292, 3);
  });

  it("is zero in microgravity", () => {
    expect(froudeTransitionSpeedMs(0, 0.9)).toBe(0);
  });

  it("accepts a different Froude number", () => {
    expect(froudeTransitionSpeedMs(9.81, 0.9, 1)).toBeCloseTo(Math.sqrt(9.81 * 0.9), 9);
  });

  it("rejects negative or non-finite arguments", () => {
    expect(() => froudeTransitionSpeedMs(-1, 0.9)).toThrow(/gEnvMs2/);
    expect(() => froudeTransitionSpeedMs(9.81, Number.NaN)).toThrow(/legLengthM/);
    expect(() => froudeTransitionSpeedMs(9.81, 0.9, -0.5)).toThrow(/froude/);
  });
});
