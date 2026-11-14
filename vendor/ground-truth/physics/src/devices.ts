/**
 * Device and environment models: the correction terms that make a session in one
 * gravity comparable with a session in another. Source for every formula is
 * docs/strategy.md §2 ("The energy model, and its honest limits") unless a
 * comment says otherwise. Pure functions on plain numbers, SI units.
 */

import { STANDARD_GRAVITY_MS2 } from "./constants";
import { requireFinite, requireInRange, requireNonNegative, requirePositive } from "./validate";

// ---------------------------------------------------------------------------
// Cycle ergometer
// ---------------------------------------------------------------------------

/**
 * CEVIS dynamometer correction, P_actual = 0.98 × P_displayed − 11.8 (W).
 * Source: NASA/TP-2007-214760 (https://ntrs.nasa.gov/api/citations/20070023931/downloads/20070023931.pdf),
 * quoted in docs/strategy.md §2 "Cycle ergometer". Displayed watts overstate
 * delivered power; delivered power cannot be negative, so the result is floored at 0.
 */
const ERGOMETER_GAIN = 0.98;
const ERGOMETER_OFFSET_W = 11.8;

export function ergometerActualPowerW(displayedPowerW: number): number {
  requireFinite("displayedPowerW", displayedPowerW);
  return Math.max(0, ERGOMETER_GAIN * displayedPowerW - ERGOMETER_OFFSET_W);
}

/**
 * Mechanical work delivered, ∫ P_actual dt, by the trapezoid rule over the
 * corrected power. Neither CEVIS nor FERGO reports cumulative work, so the
 * integration is done here (brief §2).
 */
export function ergometerWorkJ(samples: readonly { tS: number; displayedPowerW: number }[]): number {
  if (samples.length < 2) {
    throw new RangeError(`samples must contain at least 2 samples, got ${samples.length}`);
  }
  let previousT = Number.NEGATIVE_INFINITY;
  const power = samples.map((s, i) => {
    requireFinite(`samples[${i}].tS`, s.tS);
    if (s.tS <= previousT) {
      throw new RangeError(`samples[${i}].tS must be greater than samples[${i - 1}].tS (time must be strictly increasing)`);
    }
    previousT = s.tS;
    return ergometerActualPowerW(s.displayedPowerW);
  });
  let workJ = 0;
  for (let i = 0; i < samples.length - 1; i++) {
    const dt = (samples[i + 1] as { tS: number }).tS - (samples[i] as { tS: number }).tS;
    workJ += ((power[i] as number) + (power[i + 1] as number)) * 0.5 * dt;
  }
  return workJ;
}

// ---------------------------------------------------------------------------
// Body-weight replacement
// ---------------------------------------------------------------------------

/** F_total = F_device + m · g_env (brief §2, "Body-weight replacement"). g_env ≈ 0 on the ISS. */
export function totalForceN(deviceForceN: number, massKg: number, gEnvMs2: number): number {
  requireFinite("deviceForceN", deviceForceN);
  requireNonNegative("massKg", massKg);
  requireNonNegative("gEnvMs2", gEnvMs2);
  return deviceForceN + massKg * gEnvMs2;
}

/**
 * F_device = F_target − m · g_env (brief §2). A negative result means the body's own
 * weight in this environment already exceeds the target, so no device force is needed.
 */
export function deviceForceForEarthEquivalenceN(targetForceN: number, massKg: number, gEnvMs2: number): number {
  requireFinite("targetForceN", targetForceN);
  requireNonNegative("massKg", massKg);
  requireNonNegative("gEnvMs2", gEnvMs2);
  return targetForceN - massKg * gEnvMs2;
}

// ---------------------------------------------------------------------------
// Treadmill with subject load device
// ---------------------------------------------------------------------------

/**
 * F_eff = m · g_env + F_SLD, with F_SLD = supportFraction × m × 1 g (brief §2,
 * "Treadmill (T2 / COLBERT)": the harness is the gravity). supportFraction is the
 * subject load device as a fraction of 1 g body weight, in [0, 1].
 */
export function treadmillEffectiveForceN(massKg: number, gEnvMs2: number, supportFraction: number): number {
  requireNonNegative("massKg", massKg);
  requireNonNegative("gEnvMs2", gEnvMs2);
  requireInRange("supportFraction", supportFraction, 0, 1);
  return massKg * gEnvMs2 + supportFraction * massKg * STANDARD_GRAVITY_MS2;
}

// ---------------------------------------------------------------------------
// ARED
// ---------------------------------------------------------------------------

/**
 * Modelling choices:
 *  - Over a stroke that starts and ends at rest the flywheel's inertial term does no
 *    net work, so concentric work is the pneumatic setting times the stroke. This
 *    assumes a lossless flywheel and a constant pneumatic force (the brief says
 *    "nearly constant"); friction and any force ripple are not modelled.
 *  - Eccentric work is eccentricRatio × concentric, ratio <= 0.90 (brief §2:
 *    W_eccentric <= 0.90 × W_concentric); the default is that upper bound.
 *  - Peak force adds an inertial term M_eff × a_peak to the setting, for a sinusoidal
 *    stroke of amplitude stroke/2 and period T: a_peak = (stroke / 2)(2π / T)².
 */
const ARED_MAX_ECCENTRIC_RATIO = 0.9; // brief §2: eccentric runs at <= 90 % of concentric

/**
 * Both figures are non-negative. `eccentricMagnitudeJ` is a MAGNITUDE, not a signed work:
 * the signed (negative) counterpart is `-eccentricMagnitudeJ`, the sign convention of
 * `trajectoryWork().negativeWorkJ`, which is <= 0.
 */
export function aredRepWorkJ(
  settingN: number,
  strokeM: number,
  eccentricRatio: number = ARED_MAX_ECCENTRIC_RATIO,
): { concentricJ: number; eccentricMagnitudeJ: number } {
  requireNonNegative("settingN", settingN);
  requireNonNegative("strokeM", strokeM);
  requireInRange("eccentricRatio", eccentricRatio, 0, ARED_MAX_ECCENTRIC_RATIO);
  const concentricJ = settingN * strokeM;
  return { concentricJ, eccentricMagnitudeJ: eccentricRatio * concentricJ };
}

/** Peak acceleration of a sinusoidal stroke of the given length and period, m/s². */
function sinusoidalPeakAccelerationMs2(strokeM: number, periodS: number): number {
  return (strokeM / 2) * ((2 * Math.PI) / periodS) ** 2;
}

/**
 * Flywheel inertial force at the lift bar at the brief's anchor: "up to +91 kgf
 * (≈893 N) at the 600 lbf setting over a 30 in stroke at a 2 s rep period"
 * (docs/strategy.md §2, "ARED"; NTRS 20060028227).
 */
const ARED_ANCHOR_INERTIAL_FORCE_N = 893;
const ARED_ANCHOR_STROKE_M = 0.762; // 30 in
const ARED_ANCHOR_PERIOD_S = 2;

/**
 * CALIBRATED, not published: the effective flywheel mass at the lift bar that
 * reproduces the brief's +893 N anchor at 2669 N (600 lbf), 0.762 m stroke, 2 s period.
 * a_peak = 0.381 × π² = 3.7603 m/s², so M_eff = 893 / 3.7603 ≈ 237.5 kg. Computed from
 * the anchor rather than hard-coded; it is a fit to one point, so treat peak forces away
 * from that anchor as a model, not a measurement.
 *
 * Three assumptions stand behind it:
 *  1. M_eff is taken to be independent of the load setting. The brief states the anchor
 *     only "at the 600 lbf setting"; at any other setting the model adds the same
 *     M_eff × a_peak (tested as a property, not verified against a device).
 *  2. The brief says "up to +91 kgf", so +893 N is an upper bound. This model treats it as
 *     the value reached by an ideal sinusoidal stroke; a real rep may produce less.
 *  3. The work claim in aredRepWorkJ assumes a lossless flywheel and a constant pneumatic force.
 *
 * Naming note: the brief calls this term "velocity-dependent" while writing it as
 * F_flywheel(ẍ) and placing its peak at the bottom of the stroke. This model follows the
 * formula and the timing sentence: the term is proportional to acceleration.
 */
export const ARED_FLYWHEEL_EFFECTIVE_MASS_KG =
  ARED_ANCHOR_INERTIAL_FORCE_N / sinusoidalPeakAccelerationMs2(ARED_ANCHOR_STROKE_M, ARED_ANCHOR_PERIOD_S);

export function aredPeakForceN(settingN: number, strokeM: number, repPeriodS: number): number {
  requireNonNegative("settingN", settingN);
  requireNonNegative("strokeM", strokeM);
  requirePositive("repPeriodS", repPeriodS);
  return settingN + ARED_FLYWHEEL_EFFECTIVE_MASS_KG * sinusoidalPeakAccelerationMs2(strokeM, repPeriodS);
}

// ---------------------------------------------------------------------------
// Walk-run transition
// ---------------------------------------------------------------------------

/** Froude number at the walk-run transition, Fr ≈ 0.5 (brief §2, "Partial gravity is not a scaled version of Earth"). */
const FROUDE_WALK_RUN = 0.5;

/**
 * v_transition = √(Fr · g · L), L = leg length (brief §2). Zero in microgravity.
 * On the T2 treadmill the relevant gravity is the harness-supplied one
 * (`supportFraction × 9.81`), not the environment's 0: pass that as `gEnvMs2`.
 */
export function froudeTransitionSpeedMs(gEnvMs2: number, legLengthM: number, froude: number = FROUDE_WALK_RUN): number {
  requireNonNegative("gEnvMs2", gEnvMs2);
  requireNonNegative("legLengthM", legLengthM);
  requireNonNegative("froude", froude);
  return Math.sqrt(froude * gEnvMs2 * legLengthM);
}
