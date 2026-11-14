import { describe, expect, it } from "vitest";
import { EYE_TO_ANKLE_FRACTION_OF_STATURE, MIN_KNOWN_LENGTH_SPAN, metersPerUnitFromKnownLength, metersPerUnitFromStature, toMetersUp, type PoseFrame } from "../src/index";
import { lcg, minJerk, syntheticSession } from "./helpers";

describe("metersPerUnitFromKnownLength", () => {
  it("a 1.0 m reference spanning 0.2 to 0.7 of the frame is 2.0 m per unit, in either order", () => {
    expect(metersPerUnitFromKnownLength(1.0, 0.2, 0.7)).toBeCloseTo(2.0, 12);
    expect(metersPerUnitFromKnownLength(1.0, 0.7, 0.2)).toBeCloseTo(2.0, 12);
    expect(metersPerUnitFromKnownLength(0.45, 0.31, 0.49)).toBeCloseTo(0.45 / 0.18, 12);
  });

  it("throws when the span is under 0.05 of the frame", () => {
    expect(MIN_KNOWN_LENGTH_SPAN).toBe(0.05);
    expect(() => metersPerUnitFromKnownLength(1.0, 0.5, 0.52)).toThrow(RangeError);
    expect(() => metersPerUnitFromKnownLength(1.0, 0.5, 0.52)).toThrow(/span/);
    expect(() => metersPerUnitFromKnownLength(1.0, 0.5, 0.5)).toThrow(/span/);
    expect(metersPerUnitFromKnownLength(1.0, 0.5, 0.75)).toBeCloseTo(4, 12);
    expect(metersPerUnitFromKnownLength(0.1, 0.25, 0.5)).toBeCloseTo(0.4, 12);
  });

  it("rejects a non-positive length and non-finite coordinates", () => {
    expect(() => metersPerUnitFromKnownLength(0, 0.2, 0.7)).toThrow(/lengthM/);
    expect(() => metersPerUnitFromKnownLength(-1, 0.2, 0.7)).toThrow(/lengthM/);
    expect(() => metersPerUnitFromKnownLength(Number.NaN, 0.2, 0.7)).toThrow(/lengthM/);
    expect(() => metersPerUnitFromKnownLength(1, Number.NaN, 0.7)).toThrow(/yA/);
    expect(() => metersPerUnitFromKnownLength(1, 0.2, Number.POSITIVE_INFINITY)).toThrow(/yB/);
  });
});

describe("metersPerUnitFromStature", () => {
  it("1.80 m, eye at 0.20 and ankle at 0.80 of the frame: 0.897 × 1.80 / 0.60 = 2.691", () => {
    expect(EYE_TO_ANKLE_FRACTION_OF_STATURE).toBe(0.897);
    expect(metersPerUnitFromStature(1.8, 0.2, 0.8)).toBeCloseTo(2.691, 3);
  });

  it("rejects an ankle at or above the eye, or a span under 0.2 of the frame", () => {
    expect(() => metersPerUnitFromStature(1.8, 0.8, 0.2)).toThrow(RangeError);
    expect(() => metersPerUnitFromStature(1.8, 0.8, 0.2)).toThrow(/ankleY/);
    expect(() => metersPerUnitFromStature(1.8, 0.5, 0.5)).toThrow(RangeError);
    expect(() => metersPerUnitFromStature(1.8, 0.4, 0.5)).toThrow(RangeError); // span 0.1
    expect(() => metersPerUnitFromStature(1.8, 0.4, 0.5)).toThrow(/span/);
  });

  it("accepts a span of exactly 0.2", () => {
    expect(metersPerUnitFromStature(1.8, 0.3, 0.5)).toBeCloseTo((0.897 * 1.8) / 0.2, 9);
  });

  it("rejects a non-positive or non-finite stature and non-finite landmarks", () => {
    expect(() => metersPerUnitFromStature(0, 0.2, 0.8)).toThrow(/statureM/);
    expect(() => metersPerUnitFromStature(-1.8, 0.2, 0.8)).toThrow(/statureM/);
    expect(() => metersPerUnitFromStature(Number.NaN, 0.2, 0.8)).toThrow(/statureM/);
    expect(() => metersPerUnitFromStature(1.8, Number.NaN, 0.8)).toThrow(/eyeY/);
    expect(() => metersPerUnitFromStature(1.8, 0.2, Number.POSITIVE_INFINITY)).toThrow(/ankleY/);
  });
});

describe("toMetersUp", () => {
  const frame = (tS: number, wristY: number): PoseFrame => ({ tS, wristY, visibility: 1 });

  it("wristY 0.6 → 0.4 at scale 2.5 is 0 → 0.5 m: moving up the image is positive", () => {
    const out = toMetersUp([frame(0, 0.6), frame(1, 0.4)], 2.5);
    expect(out.map((p) => p.tS)).toEqual([0, 1]);
    expect(out[0]!.yM).toBeCloseTo(0, 12);
    expect(out[1]!.yM).toBeCloseTo(0.5, 12);
  });

  it("moving down the image is negative, and the first sample is always 0", () => {
    const out = toMetersUp([frame(0, 0.3), frame(0.1, 0.5)], 2);
    expect(out[0]!.yM).toBeCloseTo(0, 12);
    expect(out[1]!.yM).toBeCloseTo(-0.4, 12);
  });

  it("returns an empty array for no frames, and rejects a non-positive scale or non-finite wristY", () => {
    expect(toMetersUp([], 2.5)).toEqual([]);
    expect(() => toMetersUp([frame(0, 0.5)], 0)).toThrow(/metersPerUnit/);
    expect(() => toMetersUp([frame(0, 0.5)], Number.NaN)).toThrow(RangeError);
    expect(() => toMetersUp([frame(0, Number.NaN)], 2)).toThrow(/wristY/);
  });
});

describe("test helpers", () => {
  it("lcg is deterministic per seed, differs between seeds, and stays in [−1, 1)", () => {
    const a = lcg(7);
    const b = lcg(7);
    const c = lcg(8);
    const as = Array.from({ length: 1000 }, a);
    expect(as).toEqual(Array.from({ length: 1000 }, b));
    expect(as).not.toEqual(Array.from({ length: 1000 }, c));
    expect(Math.min(...as)).toBeGreaterThanOrEqual(-1);
    expect(Math.max(...as)).toBeLessThan(1);
    expect(Math.min(...as)).toBeLessThan(-0.9);
    expect(Math.max(...as)).toBeGreaterThan(0.9);
    expect(Math.abs(as.reduce((s, x) => s + x, 0) / as.length)).toBeLessThan(0.1);
  });

  it("minJerk runs 0 → 1 with the half-way value 0.5", () => {
    expect(minJerk(0)).toBe(0);
    expect(minJerk(1)).toBeCloseTo(1, 12);
    expect(minJerk(0.5)).toBeCloseTo(0.5, 12);
  });

  it("syntheticSession: rests, then reps, with the stated length, no noise reproducing the profile", () => {
    const frames = syntheticSession({ reps: 2, heightM: 0.5, upS: 1, downS: 1, restS: 0.5, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: 2.5 });
    // 0.5 + 2 × (1 + 1 + 0.5) = 5.5 s -> 331 frames
    expect(frames).toHaveLength(331);
    expect(frames[0]!.tS).toBe(0);
    const yM = toMetersUp(frames, 2.5).map((p) => p.yM);
    expect(Math.max(...yM)).toBeCloseTo(0.5, 6);
    expect(yM[30]).toBeCloseTo(0, 9); // end of the first rest
    expect(yM[60]).toBeCloseTo(0.25, 6); // half-way up the first lift (t = 1.0 s)
    expect(yM[90]).toBeCloseTo(0.5, 6); // the top (t = 1.5 s)
    expect(yM[150]).toBeCloseTo(0, 6); // lowered again (t = 2.5 s)
  });

  it("syntheticSession noise is bounded by ±noiseM and differs between seeds", () => {
    const make = (seed: number) => syntheticSession({ reps: 1, heightM: 0.5, upS: 1, downS: 1, restS: 0.5, rateHz: 60, noiseM: 0.002, seed, metersPerUnit: 2.5 });
    const clean = toMetersUp(syntheticSession({ reps: 1, heightM: 0.5, upS: 1, downS: 1, restS: 0.5, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: 2.5 }), 2.5);
    const noisy = toMetersUp(make(1), 2.5);
    // the first sample is re-zeroed, so compare differences from it: at most 2 × noiseM apart
    const worst = Math.max(...noisy.map((p, i) => Math.abs(p.yM - clean[i]!.yM)));
    expect(worst).toBeLessThanOrEqual(0.004 + 1e-12);
    expect(worst).toBeGreaterThan(0.002);
    expect(make(1)).toEqual(make(1));
    expect(make(1)).not.toEqual(make(2));
  });
});
