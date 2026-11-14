import { describe, expect, it } from "vitest";
import {
  GENC_2010_PEAK_LOAD_DECREMENT,
  LOAD_STIMULUS_EXPONENT,
  cumulativeDeficit,
  cyclesToMatch,
  dailyLoadStimulus,
} from "../src/index";

describe("dailyLoadStimulus", () => {
  it("uses the exponent 4 from the brief", () => {
    expect(LOAD_STIMULUS_EXPONENT).toBe(4);
  });

  it("one bout: 12^(1/4) × peak load", () => {
    expect(dailyLoadStimulus([{ cycles: 12, peakLoad: 2000 }])).toBeCloseTo(3722.4, 1);
  });

  it("no bouts is zero stimulus", () => {
    expect(dailyLoadStimulus([])).toBe(0);
  });

  it("peaks dominate volume: 12 cycles at 2000 beats 1200 cycles at 500", () => {
    const peak = dailyLoadStimulus([{ cycles: 12, peakLoad: 2000 }]);
    const volume = dailyLoadStimulus([{ cycles: 1200, peakLoad: 500 }]);
    expect(peak).toBeGreaterThan(volume);
    expect(peak).toBeCloseTo(3722.4, 1);
    expect(volume).toBeCloseTo(2942.8, 0);
  });

  it("is homogeneous of degree 1 in peak load: a quarter of the load is exactly a quarter of S", () => {
    const bouts = [
      { cycles: 10, peakLoad: 1000 },
      { cycles: 5, peakLoad: 2000 },
    ];
    const quartered = bouts.map((b) => ({ ...b, peakLoad: b.peakLoad * 0.25 }));
    const s = dailyLoadStimulus(bouts);
    const sQuarter = dailyLoadStimulus(quartered);
    expect(Math.abs(sQuarter - 0.25 * s) / (0.25 * s)).toBeLessThan(1e-12);
  });

  it("combines bouts as (Σ n σ^m)^(1/m)", () => {
    // (10·1000⁴ + 5·2000⁴)^(1/4) = (9e13)^(1/4)
    const s = dailyLoadStimulus([
      { cycles: 10, peakLoad: 1000 },
      { cycles: 5, peakLoad: 2000 },
    ]);
    expect(s).toBeCloseTo(3080.07, 1);
  });

  it("accepts a different exponent", () => {
    // m = 1 is the plain sum of n·σ
    expect(dailyLoadStimulus([{ cycles: 2, peakLoad: 10 }, { cycles: 3, peakLoad: 20 }], 1)).toBeCloseTo(80, 9);
  });

  it("rejects negative cycles, negative or non-finite load and a non-positive exponent", () => {
    expect(() => dailyLoadStimulus([{ cycles: -1, peakLoad: 1000 }])).toThrow(RangeError);
    expect(() => dailyLoadStimulus([{ cycles: -1, peakLoad: 1000 }])).toThrow(/cycles/);
    expect(() => dailyLoadStimulus([{ cycles: 1, peakLoad: -5 }])).toThrow(/peakLoad/);
    expect(() => dailyLoadStimulus([{ cycles: 1, peakLoad: Number.NaN }])).toThrow(RangeError);
    expect(() => dailyLoadStimulus([{ cycles: 1, peakLoad: 5 }], 0)).toThrow(/exponent/);
  });
});

describe("cyclesToMatch", () => {
  it("a quarter of the load needs 256 times the cycles", () => {
    expect(cyclesToMatch(0.25)).toBeCloseTo(256, 9);
  });

  it("applies to Genc 2010's on-orbit decrements", () => {
    expect(cyclesToMatch(1 - GENC_2010_PEAK_LOAD_DECREMENT.squat)).toBeCloseTo(66.64, 2);
    expect(cyclesToMatch(1 - GENC_2010_PEAK_LOAD_DECREMENT.walking)).toBeCloseTo(357.35, 2);
  });

  it("full load needs the same number of cycles", () => {
    expect(cyclesToMatch(1)).toBe(1);
  });

  it("rejects a zero, negative or non-finite ratio", () => {
    expect(() => cyclesToMatch(0)).toThrow(RangeError);
    expect(() => cyclesToMatch(0)).toThrow(/loadRatio/);
    expect(() => cyclesToMatch(-0.5)).toThrow(RangeError);
    expect(() => cyclesToMatch(Number.NaN)).toThrow(RangeError);
  });
});

describe("cumulativeDeficit", () => {
  it("integrates baseline − achieved over days (trapezoid)", () => {
    expect(
      cumulativeDeficit(
        [
          { day: 0, achieved: 25 },
          { day: 180, achieved: 25 },
        ],
        100,
      ),
    ).toBe(13500);
  });

  it("integrates a changing series by the trapezoid rule", () => {
    // deficits 100, 50, 0 at days 0, 10, 30: 10·75 + 20·25
    expect(
      cumulativeDeficit(
        [
          { day: 0, achieved: 0 },
          { day: 10, achieved: 50 },
          { day: 30, achieved: 100 },
        ],
        100,
      ),
    ).toBeCloseTo(1250, 9);
  });

  it("reports a surplus as a negative deficit", () => {
    // (100 − 150) × 10 days = −500
    expect(
      cumulativeDeficit(
        [
          { day: 0, achieved: 150 },
          { day: 10, achieved: 150 },
        ],
        100,
      ),
    ).toBe(-500);
  });

  it("a single point has no duration, so no deficit", () => {
    expect(cumulativeDeficit([{ day: 0, achieved: 25 }], 100)).toBe(0);
  });

  it("rejects non-increasing days and non-finite values", () => {
    expect(() =>
      cumulativeDeficit(
        [
          { day: 5, achieved: 25 },
          { day: 5, achieved: 25 },
        ],
        100,
      ),
    ).toThrow(RangeError);
    expect(() =>
      cumulativeDeficit(
        [
          { day: 5, achieved: 25 },
          { day: 3, achieved: 25 },
        ],
        100,
      ),
    ).toThrow(/day/);
    expect(() => cumulativeDeficit([{ day: 0, achieved: Number.NaN }], 100)).toThrow(/achieved/);
    expect(() => cumulativeDeficit([{ day: 0, achieved: 1 }], Number.NaN)).toThrow(/baseline/);
  });
});
