/**
 * Gravity table, in m/s². Source: docs/strategy.md §2 ("Partial gravity is not a
 * scaled version of Earth") — Moon 1.62, Mars 3.71, Earth 9.81, ISS ~10⁻⁶ g.
 *
 * ISS is 0: the brief gives ~10⁻⁶ g, which is treated as zero for every
 * calculation in this package.
 */
export const G_ENV_MS2 = {
  EARTH: 9.81,
  MARS: 3.71,
  MOON: 1.62,
  ISS: 0,
  // Free-fall coast between bodies: same as the ISS for this model (no weight, only inertia).
  TRANSIT: 0,
} as const;

/**
 * 1 g body weight reference, m/s². Source: docs/strategy.md §2, treadmill model
 * (SLD set as a fraction of 1 g body weight) and Earth gravity row of the table above.
 */
export const STANDARD_GRAVITY_MS2 = 9.81;

/**
 * Mean on-orbit decrement in single-leg peak load relative to matched Earth
 * activity, as a fraction (0.75 = 75 % lower), even at maximum device settings.
 * Source: Genc 2010 (https://pubmed.ncbi.nlm.nih.gov/20728086/), quoted in
 * docs/strategy.md §2 "Calibration anchor": 75 % running, 77 % walking, 65 % squats.
 */
export const GENC_2010_PEAK_LOAD_DECREMENT = {
  running: 0.75,
  walking: 0.77,
  squat: 0.65,
} as const;
