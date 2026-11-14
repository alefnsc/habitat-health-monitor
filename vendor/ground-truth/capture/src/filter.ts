/**
 * Zero-phase low-pass filter for position traces.
 *
 * Positions must be smoothed before they are differentiated: trajectoryWork takes first
 * and second differences, which amplify noise (packages/physics/README.md, "Noise
 * sensitivity"). A causal filter would delay the trace and shift every rep boundary, so
 * the filter runs forward then backward.
 */

import { requireFinite } from "./internal";

/** Measured in the physics review: 3–4 Hz for peak force on ~1 s lifts (packages/physics/README.md). */
export const DEFAULT_CUTOFF_HZ = 4;

/**
 * Padding on each side, in cutoff periods: a judgement call. The edge is extended by
 * three periods of the cutoff frequency, which is long enough for a second-order
 * Butterworth's start-up transient to die out before the first real sample. Exported so
 * the session gate (analyzeSession refuses a recording the padding would not fit in)
 * and the filter use the same number.
 */
export const PADDING_CUTOFF_PERIODS = 3;

/** Samples of padding on each side for a cutoff at a rate; a signal must be LONGER than this to be filtered. */
export function filterPaddingSamples(rateHz: number, cutoffHz: number): number {
  return Math.ceil((PADDING_CUTOFF_PERIODS * rateHz) / cutoffHz);
}

interface Biquad {
  b0: number;
  b1: number;
  b2: number;
  a1: number;
  a2: number;
}

/** Second-order Butterworth by the bilinear transform with pre-warping (a0 normalised to 1). */
function butterworth2(rateHz: number, cutoffHz: number): Biquad {
  const k = Math.tan((Math.PI * cutoffHz) / rateHz);
  const norm = 1 / (1 + Math.SQRT2 * k + k * k);
  const b0 = k * k * norm;
  return {
    b0,
    b1: 2 * b0,
    b2: b0,
    a1: 2 * (k * k - 1) * norm,
    a2: (1 - Math.SQRT2 * k + k * k) * norm,
  };
}

/**
 * One causal pass, direct form II transposed, started in the steady state for a constant
 * input equal to x[0] (unit DC gain: z1 = (1 − b0)·u, z2 = (b2 − a2)·u), so a constant
 * signal produces no start-up transient at all.
 */
function filterForward(x: readonly number[], c: Biquad): number[] {
  const u = x[0] as number;
  let z1 = (1 - c.b0) * u;
  let z2 = (c.b2 - c.a2) * u;
  const y: number[] = new Array<number>(x.length);
  for (let i = 0; i < x.length; i++) {
    const xi = x[i] as number;
    const yi = c.b0 * xi + z1;
    z1 = c.b1 * xi - c.a1 * yi + z2;
    z2 = c.b2 * xi - c.a2 * yi;
    y[i] = yi;
  }
  return y;
}

/**
 * Second-order Butterworth, applied forward then backward (zero phase), with reflected
 * edge padding. Each end is extended by a point reflection about the end sample,
 * x[−j] = 2·x[0] − x[j] (the same on the right), which keeps both the value and the
 * slope continuous at the edge; a constant input stays constant to the last sample.
 * The two passes square the magnitude response: the amplitude gain at f is 1/(1 + r⁴)
 * with r = tan(π f / fs) / tan(π fc / fs), exactly 0.5 at the cutoff. The input is
 * not modified. Needs more samples than the padding, ceil(3·rateHz/cutoffHz) per side.
 */
export function lowPassZeroPhase(values: readonly number[], rateHz: number, cutoffHz: number = DEFAULT_CUTOFF_HZ): number[] {
  requireFinite("rateHz", rateHz);
  if (rateHz <= 0) throw new RangeError(`rateHz must be > 0, got ${rateHz}`);
  requireFinite("cutoffHz", cutoffHz);
  if (cutoffHz <= 0 || cutoffHz >= rateHz / 2) {
    throw new RangeError(`cutoffHz must be > 0 and below rateHz / 2 (${rateHz / 2}), got ${cutoffHz}`);
  }
  values.forEach((v, i) => requireFinite(`values[${i}]`, v));
  const pad = filterPaddingSamples(rateHz, cutoffHz);
  if (values.length <= pad) {
    throw new RangeError(`values must contain more than ${pad} samples for a ${cutoffHz} Hz cutoff at ${rateHz} Hz, got ${values.length}`);
  }

  const n = values.length;
  const first = values[0] as number;
  const last = values[n - 1] as number;
  const padded: number[] = new Array<number>(n + 2 * pad);
  for (let j = 1; j <= pad; j++) {
    padded[pad - j] = 2 * first - (values[j] as number);
    padded[pad + n - 1 + j] = 2 * last - (values[n - 1 - j] as number);
  }
  for (let i = 0; i < n; i++) padded[pad + i] = values[i] as number;

  const c = butterworth2(rateHz, cutoffHz);
  const forward = filterForward(padded, c);
  const backward = filterForward(forward.reverse(), c).reverse();
  return backward.slice(pad, pad + n);
}
