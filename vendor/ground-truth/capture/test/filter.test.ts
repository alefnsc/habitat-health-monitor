import { describe, expect, it } from "vitest";
import { DEFAULT_CUTOFF_HZ, lowPassZeroPhase } from "../src/index";
import { minJerk } from "./helpers";

const FS = 60;
const FC = 4;
const N = 600; // 10 s
const MID_START = 150; // the middle half: samples 150..449 = 5 s, a whole number of cycles at 1, 4 and 20 Hz
const MID_END = 450;

const sine = (f: number, phase = 0): number[] => Array.from({ length: N }, (_, i) => Math.sin(2 * Math.PI * f * (i / FS) + phase));

/** Amplitude and phase of the component at `f` over the middle half, by projection (exact for a whole number of cycles). */
function tone(x: readonly number[], f: number): { amplitude: number; phase: number } {
  let c = 0;
  let s = 0;
  for (let i = MID_START; i < MID_END; i++) {
    const w = 2 * Math.PI * f * (i / FS);
    c += (x[i] as number) * Math.cos(w);
    s += (x[i] as number) * Math.sin(w);
  }
  const k = 2 / (MID_END - MID_START);
  return { amplitude: k * Math.hypot(c, s), phase: Math.atan2(c, s) }; // x ≈ A sin(w + phase)
}

/** The theoretical amplitude gain of the forward-backward pass: 1 / (1 + r⁴), r = tan(π f / fs) / tan(π fc / fs). */
const theoreticalGain = (f: number): number => 1 / (1 + (Math.tan((Math.PI * f) / FS) / Math.tan((Math.PI * FC) / FS)) ** 4);

describe("lowPassZeroPhase", () => {
  it("the default cutoff is 4 Hz", () => {
    expect(DEFAULT_CUTOFF_HZ).toBe(4);
    const x = sine(3);
    expect(lowPassZeroPhase(x, FS)).toEqual(lowPassZeroPhase(x, FS, 4));
    expect(lowPassZeroPhase(x, FS, 2)).not.toEqual(lowPassZeroPhase(x, FS));
  });

  it("a constant input comes out unchanged within 1e-9, including the first and last samples", () => {
    for (const c of [0, 1, -3.7, 12345.678]) {
      const out = lowPassZeroPhase(new Array<number>(N).fill(c), FS, FC);
      expect(out).toHaveLength(N);
      expect(out[0]).toBeCloseTo(c, 9);
      expect(out[N - 1]).toBeCloseTo(c, 9);
      expect(Math.max(...out.map((v) => Math.abs(v - c)))).toBeLessThan(1e-9 * Math.max(1, Math.abs(c)));
    }
  });

  it("a linear ramp is unchanged within 1e-6 in the middle half", () => {
    const ramp = Array.from({ length: N }, (_, i) => 0.01 * i - 1);
    const out = lowPassZeroPhase(ramp, FS, FC);
    for (let i = MID_START; i < MID_END; i++) expect(Math.abs((out[i] as number) - (ramp[i] as number))).toBeLessThan(1e-6);
  });

  it("1 Hz passes with gain 0.9963 (±0.002)", () => {
    const { amplitude } = tone(lowPassZeroPhase(sine(1), FS, FC), 1);
    expect(amplitude).toBeGreaterThan(0.9963 - 0.002);
    expect(amplitude).toBeLessThan(0.9963 + 0.002);
    expect(amplitude).toBeCloseTo(theoreticalGain(1), 4);
  });

  it("4 Hz, the cutoff, is halved by the two passes (gain 0.5 ± 0.01)", () => {
    const { amplitude } = tone(lowPassZeroPhase(sine(4), FS, FC), 4);
    expect(amplitude).toBeGreaterThan(0.49);
    expect(amplitude).toBeLessThan(0.51);
    expect(amplitude).toBeCloseTo(theoreticalGain(4), 4);
  });

  it("20 Hz is gone (gain < 0.001)", () => {
    const { amplitude } = tone(lowPassZeroPhase(sine(20), FS, FC), 20);
    expect(amplitude).toBeLessThan(0.001);
  });

  it("follows the 1/(1 + r⁴) response at other frequencies, so the cutoff really is the one asked for", () => {
    for (const f of [0.5, 2, 3, 6, 10]) {
      expect(tone(lowPassZeroPhase(sine(f), FS, FC), f).amplitude).toBeCloseTo(theoreticalGain(f), 3);
    }
    // a different cutoff moves the half-gain point
    expect(tone(lowPassZeroPhase(sine(6), FS, 6), 6).amplitude).toBeCloseTo(0.5, 2);
  });

  it("is zero phase: the peaks of a 1 Hz sine land on the same sample indices (±1), and the phase is unchanged", () => {
    const input = sine(1);
    const out = lowPassZeroPhase(input, FS, FC);
    const peaks = (x: readonly number[]): number[] => {
      const found: number[] = [];
      for (let i = MID_START; i < MID_END; i++) if ((x[i] as number) > (x[i - 1] as number) && (x[i] as number) >= (x[i + 1] as number)) found.push(i);
      return found;
    };
    const inPeaks = peaks(input);
    const outPeaks = peaks(out);
    expect(inPeaks.length).toBe(5);
    expect(outPeaks.length).toBe(inPeaks.length);
    outPeaks.forEach((p, k) => expect(Math.abs(p - (inPeaks[k] as number))).toBeLessThanOrEqual(1));
    expect(tone(out, 1).phase).toBeCloseTo(tone(input, 1).phase, 6);
    // and at a frequency where a causal filter would lag badly
    expect(tone(lowPassZeroPhase(sine(3), FS, FC), 3).phase).toBeCloseTo(0, 6);
  });

  it("a symmetric pulse stays symmetric about the same centre", () => {
    const centre = 150;
    const pulse = Array.from({ length: 2 * centre + 1 }, (_, i) => Math.exp(-(((i - centre) / 12) ** 2)));
    const out = lowPassZeroPhase(pulse, FS, FC);
    for (let k = 0; k <= centre; k++) expect(Math.abs((out[centre - k] as number) - (out[centre + k] as number))).toBeLessThan(1e-9);
    expect(out.indexOf(Math.max(...out))).toBe(centre);
  });

  it("reflected padding keeps the ends of a lift that starts and ends at rest where they were", () => {
    const lift = Array.from({ length: 121 }, (_, i) => 0.5 * minJerk(Math.min(1, Math.max(0, (i - 30) / 60))));
    const out = lowPassZeroPhase(lift, FS, FC);
    expect(Math.abs((out[0] as number) - (lift[0] as number))).toBeLessThan(2e-3);
    expect(Math.abs((out[120] as number) - (lift[120] as number))).toBeLessThan(2e-3);
  });

  it("a trace that starts half-way through a lift (non-zero slope at the edge) keeps its first sample within 1 mm", () => {
    // Positions of a 0.5 m, 1 s minimum-jerk lift from t = 0.5 s (the peak-velocity point, 0.94 m/s) to 2.5 s,
    // the position held at 0.5 m after t = 1 s. Point reflection (x[-j] = 2 x[0] - x[j]) keeps value and slope
    // across the edge: first-sample error 0.00 mm. A mirror reflection (x[-j] = x[j]) measured 26.6 mm, and
    // constant padding with the edge value is worse.
    const trace = Array.from({ length: 121 }, (_, i) => 0.5 * minJerk(Math.min(1, 0.5 + i / FS)));
    const out = lowPassZeroPhase(trace, FS, FC);
    expect(Math.abs((out[0] as number) - (trace[0] as number))).toBeLessThan(1e-3);
    // the slope at the far edge is zero (the lift is over), so that edge is easy; the near edge is the test
    expect(Math.abs((out[1] as number) - (trace[1] as number))).toBeLessThan(2e-3);
  });

  it("does not modify its input", () => {
    const x = sine(1);
    const copy = [...x];
    lowPassZeroPhase(x, FS, FC);
    expect(x).toEqual(copy);
  });

  describe("invalid input", () => {
    it("rejects a cutoff at or above Nyquist, or non-positive", () => {
      const x = sine(1);
      expect(() => lowPassZeroPhase(x, FS, 30)).toThrow(RangeError);
      expect(() => lowPassZeroPhase(x, FS, 30)).toThrow(/cutoffHz/);
      expect(() => lowPassZeroPhase(x, FS, 40)).toThrow(/cutoffHz/);
      expect(() => lowPassZeroPhase(x, FS, 0)).toThrow(/cutoffHz/);
      expect(() => lowPassZeroPhase(x, FS, Number.NaN)).toThrow(/cutoffHz/);
    });

    it("rejects too few samples for the padding (5 samples; and one fewer than the padding needs)", () => {
      expect(() => lowPassZeroPhase([1, 2, 3, 4, 5], FS, FC)).toThrow(RangeError);
      expect(() => lowPassZeroPhase([1, 2, 3, 4, 5], FS, FC)).toThrow(/values/);
      expect(() => lowPassZeroPhase([], FS, FC)).toThrow(RangeError);
      expect(() => lowPassZeroPhase(new Array<number>(45).fill(0), FS, FC)).toThrow(RangeError);
      expect(lowPassZeroPhase(new Array<number>(46).fill(0), FS, FC)).toHaveLength(46);
    });

    it("rejects a bad rate and non-finite values", () => {
      expect(() => lowPassZeroPhase(sine(1), 0, FC)).toThrow(/rateHz/);
      expect(() => lowPassZeroPhase(sine(1), Number.NaN, FC)).toThrow(/rateHz/);
      const bad = sine(1);
      bad[10] = Number.NaN;
      expect(() => lowPassZeroPhase(bad, FS, FC)).toThrow(/values\[10\]/);
    });
  });
});
