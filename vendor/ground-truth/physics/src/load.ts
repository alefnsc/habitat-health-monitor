/**
 * Skeletal load stimulus and cumulative deficit: load ACCOUNTING, not bone-loss
 * inference. These functions do bookkeeping on a load an operator or a sensor
 * supplied; they do not measure bone and do not predict it.
 *
 * Source: docs/strategy.md §2, "The load model" (Carter / Whalen / Beaupré daily
 * load stimulus; the Turner / Robling saturating refinement is out of scope).
 *
 * Loads are in any ONE consistent unit (newtons or body weights). S has that unit times
 * cycles^(1/m), so it is comparable only between calls that use the same unit and exponent.
 */

import { requireFinite, requireNonNegative, requirePositive } from "./validate";

export interface LoadBout {
  cycles: number;
  peakLoad: number; // any one consistent unit (N or body weights)
}

/** Exponent m in S_day = (Σ n_i σ_i^m)^(1/m), m ≈ 4 so that peaks dominate and volume does not. Source: Carter / Whalen / Beaupré, brief §2. */
export const LOAD_STIMULUS_EXPONENT = 4;

/** S_day = ( Σ n_i · σ_i^m )^(1/m). Zero for no bouts. Homogeneous of degree 1 in peakLoad. */
export function dailyLoadStimulus(bouts: readonly LoadBout[], exponent: number = LOAD_STIMULUS_EXPONENT): number {
  requirePositive("exponent", exponent);
  let sum = 0;
  bouts.forEach((b, i) => {
    requireNonNegative(`bouts[${i}].cycles`, b.cycles);
    requireNonNegative(`bouts[${i}].peakLoad`, b.peakLoad);
    sum += b.cycles * b.peakLoad ** exponent;
  });
  return sum ** (1 / exponent);
}

/**
 * How many times more cycles are needed to match a stimulus when peak load is
 * `loadRatio` of the reference: loadRatio^(−m). With m = 4 a quarter of the load
 * needs 256 times the cycles. (S itself only falls by the factor loadRatio.)
 *
 * Passing `1 − Genc decrement` as the ratio assumes the stress at the bone site scales
 * with the measured in-shoe force. That is an assumption of this package; Genc 2010
 * reports the in-shoe force, not bone-site stress.
 */
export function cyclesToMatch(loadRatio: number, exponent: number = LOAD_STIMULUS_EXPONENT): number {
  requirePositive("loadRatio", loadRatio);
  requirePositive("exponent", exponent);
  return loadRatio ** -exponent;
}

/**
 * Deficit(T) = ∫ ( S_baseline − S_achieved(t) ) dt, trapezoid over days, in
 * stimulus-units × days. A surplus (achieved above baseline) is allowed and
 * comes out negative. Fewer than two points span no time, so the deficit is 0.
 */
export function cumulativeDeficit(series: readonly { day: number; achieved: number }[], baseline: number): number {
  requireFinite("baseline", baseline);
  let previousDay = Number.NEGATIVE_INFINITY;
  series.forEach((p, i) => {
    requireFinite(`series[${i}].day`, p.day);
    requireFinite(`series[${i}].achieved`, p.achieved);
    if (p.day <= previousDay) {
      throw new RangeError(`series[${i}].day must be greater than series[${i - 1}].day (days must be strictly increasing)`);
    }
    previousDay = p.day;
  });
  let deficit = 0;
  for (let i = 0; i < series.length - 1; i++) {
    const a = series[i] as { day: number; achieved: number };
    const b = series[i + 1] as { day: number; achieved: number };
    deficit += (baseline - (a.achieved + b.achieved) / 2) * (b.day - a.day);
  }
  return deficit;
}
