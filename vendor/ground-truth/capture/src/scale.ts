/**
 * Conversion from normalised image units to metres. This file is the ONE place where
 * image coordinates (y down) become metres (y up).
 *
 * Scale is the largest single source of error in the pipeline: a 3 % error in
 * metres-per-unit is a 3 % error in work and in range of motion.
 */

import type { PoseFrame } from "./frames";
import { requireFinite } from "./internal";

/**
 * Eye-to-ankle distance as a fraction of stature: eye height 0.936·H minus ankle
 * height 0.039·H = 0.897·H (Drillis & Contini segment proportions, as tabulated in
 * Winter, Biomechanics and Motor Control of Human Movement).
 *
 * ANTHROPOMETRIC ESTIMATE — verify against the source before the hackathon.
 * The two proportions are quoted from memory of a standard table, not checked here.
 */
export const EYE_TO_ANKLE_FRACTION_OF_STATURE = 0.897;

/** Judgement call: a calibration frame in which the person fills under a fifth of the frame height is too coarse to scale from. */
export const MIN_CALIBRATION_SPAN = 0.2;

/**
 * Metres per normalised image unit from a side-on, upright calibration frame:
 * (0.897 · statureM) / (ankleY − eyeY). y is down, so the ankle has the larger y.
 * Throws if the ankle is not below the eye or the span is under 0.2 of the frame.
 */
export function metersPerUnitFromStature(statureM: number, eyeY: number, ankleY: number): number {
  requireFinite("statureM", statureM);
  if (statureM <= 0) throw new RangeError(`statureM must be > 0, got ${statureM}`);
  requireFinite("eyeY", eyeY);
  requireFinite("ankleY", ankleY);
  if (ankleY <= eyeY) throw new RangeError(`ankleY must be greater than eyeY (y points down), got eyeY=${eyeY}, ankleY=${ankleY}`);
  const span = ankleY - eyeY;
  if (span < MIN_CALIBRATION_SPAN) {
    throw new RangeError(`eye-to-ankle span must be at least ${MIN_CALIBRATION_SPAN} of the frame, got ${span}`);
  }
  return (EYE_TO_ANKLE_FRACTION_OF_STATURE * statureM) / span;
}

/** Judgement call: a reference length spanning under a twentieth of the frame height is too coarse to scale from. */
export const MIN_KNOWN_LENGTH_SPAN = 0.05;

/**
 * Metres per normalised image unit from an object of known length held vertically in the
 * lifting hand, at the wrist's depth, in one frame: lengthM / |yB − yA|, where yA and yB
 * are the image heights of its two ends. Order does not matter. Preferred to the stature
 * method because the reference is at the wrist's own distance from the camera (see the
 * README, "Scale"). Throws if the length is not > 0 or the span is under 0.05 of the frame.
 */
export function metersPerUnitFromKnownLength(lengthM: number, yA: number, yB: number): number {
  requireFinite("lengthM", lengthM);
  if (lengthM <= 0) throw new RangeError(`lengthM must be > 0, got ${lengthM}`);
  requireFinite("yA", yA);
  requireFinite("yB", yB);
  const span = Math.abs(yB - yA);
  if (span < MIN_KNOWN_LENGTH_SPAN) {
    throw new RangeError(`the reference's span must be at least ${MIN_KNOWN_LENGTH_SPAN} of the frame, got ${span}`);
  }
  return lengthM / span;
}

/**
 * Wrist height in metres, up positive: yM = −wristY · metersPerUnit, shifted so the
 * first sample is 0.
 */
export function toMetersUp(frames: readonly PoseFrame[], metersPerUnit: number): { tS: number; yM: number }[] {
  requireFinite("metersPerUnit", metersPerUnit);
  if (metersPerUnit <= 0) throw new RangeError(`metersPerUnit must be > 0, got ${metersPerUnit}`);
  frames.forEach((f, i) => {
    requireFinite(`frames[${i}].tS`, f.tS);
    requireFinite(`frames[${i}].wristY`, f.wristY);
  });
  const origin = frames.length > 0 ? -(frames[0] as PoseFrame).wristY * metersPerUnit : 0;
  return frames.map((f) => ({ tS: f.tS, yM: -f.wristY * metersPerUnit - origin }));
}
