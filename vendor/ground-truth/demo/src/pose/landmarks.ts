/**
 * Pose-model landmarks to the capture package's PoseFrame. Pure.
 *
 * The indices are the MediaPipe pose model's 33-landmark topology. The installed package's
 * `PoseLandmarker.POSE_CONNECTIONS` confirms the pairing used here: its connection chains run
 * 0-1-2-3-7 and 0-4-5-6-8 (eyes 2 and 5), 11-13-15 and 12-14-16 (wrists 15 and 16), and 23-25-27 and
 * 24-26-28 (ankles 27 and 28). The package's types do not name the landmarks; the left and right
 * names are from the model's documentation. Which is which does not matter to the maths, because the
 * side is chosen by visibility (`pickSide`).
 *
 * y is passed through unchanged (normalised, pointing down): the capture package converts it, once.
 */

import type { PoseFrame } from "@ground-truth/capture";

export const LANDMARK = { LEFT_EYE: 2, RIGHT_EYE: 5, LEFT_WRIST: 15, RIGHT_WRIST: 16, LEFT_ANKLE: 27, RIGHT_ANKLE: 28 } as const;

export type Side = "LEFT" | "RIGHT";

export interface Landmark {
  x: number;
  y: number;
  visibility?: number;
}

/** A calibration landmark below this visibility is not read (the capture package's own visibility threshold is also 0.5). */
export const CALIBRATION_MIN_VISIBILITY = 0.5;

const LOST = (tS: number): PoseFrame => ({ tS, wristY: 0, visibility: 0 });

/** Visibility as a number, 0 for anything that is not one: an unknown confidence is not trusted. */
function visibilityOf(landmark: Landmark | undefined): number {
  const v = landmark?.visibility;
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

/**
 * The tracked wrist of one frame. No detection, a pose that stops before the wrist, or a wrist
 * without a usable y is `visibility: 0` with `wristY: 0` (never the last position, never a high
 * visibility). A wrist with no visibility field is also visibility 0.
 */
export function toPoseFrame(tS: number, landmarks: readonly Landmark[] | undefined, side: Side): PoseFrame {
  const wrist = landmarks?.[side === "LEFT" ? LANDMARK.LEFT_WRIST : LANDMARK.RIGHT_WRIST];
  if (!wrist || !Number.isFinite(wrist.y)) return LOST(tS);
  return { tS, wristY: wrist.y, visibility: visibilityOf(wrist) };
}

/** The wrist with the higher mean visibility over the samples (a frame with no detection counts 0). LEFT on a tie or with no samples. */
export function pickSide(samples: readonly (readonly Landmark[])[]): Side {
  let left = 0;
  let right = 0;
  for (const landmarks of samples) {
    left += visibilityOf(landmarks[LANDMARK.LEFT_WRIST]);
    right += visibilityOf(landmarks[LANDMARK.RIGHT_WRIST]);
  }
  return right > left ? "RIGHT" : "LEFT";
}

/** The eye and ankle heights of the chosen side, for the stature method; null when either landmark is missing or under 0.5 visibility. */
export function calibrationFromLandmarks(landmarks: readonly Landmark[], side: Side): { eyeY: number; ankleY: number } | null {
  const eye = landmarks[side === "LEFT" ? LANDMARK.LEFT_EYE : LANDMARK.RIGHT_EYE];
  const ankle = landmarks[side === "LEFT" ? LANDMARK.LEFT_ANKLE : LANDMARK.RIGHT_ANKLE];
  if (!eye || !ankle) return null;
  if (visibilityOf(eye) < CALIBRATION_MIN_VISIBILITY || visibilityOf(ankle) < CALIBRATION_MIN_VISIBILITY) return null;
  if (!Number.isFinite(eye.y) || !Number.isFinite(ankle.y)) return null;
  return { eyeY: eye.y, ankleY: ankle.y };
}

/** The wrist landmark of the chosen side, for drawing. Undefined when the pose stops before it. */
export function wristOf(landmarks: readonly Landmark[] | undefined, side: Side): Landmark | undefined {
  return landmarks?.[side === "LEFT" ? LANDMARK.LEFT_WRIST : LANDMARK.RIGHT_WRIST];
}

/** A pointer's height over an element as a fraction of that element's height, 0 at the top, clamped to 0..1. */
export function normalizedY(clientY: number, top: number, height: number): number {
  if (!(height > 0)) return 0;
  return Math.min(1, Math.max(0, (clientY - top) / height));
}

// ---------------------------------------------------------------------------
// The side is chosen over the RECORDED frames, once, when the recording ends
// ---------------------------------------------------------------------------

/** Both wrists of one recorded frame, each already in the capture package's shape. */
export interface WristSample {
  tS: number;
  LEFT: PoseFrame;
  RIGHT: PoseFrame;
}

export function wristSample(tS: number, landmarks: readonly Landmark[] | undefined): WristSample {
  return { tS, LEFT: toPoseFrame(tS, landmarks, "LEFT"), RIGHT: toPoseFrame(tS, landmarks, "RIGHT") };
}

/** The wrist with the higher mean visibility over the recorded frames; LEFT on a tie or with nothing recorded. */
export function pickRecordedSide(samples: readonly WristSample[]): Side {
  let left = 0;
  let right = 0;
  for (const s of samples) {
    left += s.LEFT.visibility;
    right += s.RIGHT.visibility;
  }
  return right > left ? "RIGHT" : "LEFT";
}

/** The frames of one side, for the capture package. */
export function framesOf(samples: readonly WristSample[], side: Side): PoseFrame[] {
  return samples.map((s) => s[side]);
}

/**
 * Eye and ankle heights for the stature method from ONE pose (the frozen frame's): the side whose eye and ankle are
 * more visible, falling to the other side when that one is not usable. Null when neither side has both.
 */
export function calibrationOfBestSide(landmarks: readonly Landmark[] | undefined): { side: Side; eyeY: number; ankleY: number } | null {
  if (!landmarks) return null;
  const score = (side: Side): number =>
    visibilityOf(landmarks[side === "LEFT" ? LANDMARK.LEFT_EYE : LANDMARK.RIGHT_EYE]) + visibilityOf(landmarks[side === "LEFT" ? LANDMARK.LEFT_ANKLE : LANDMARK.RIGHT_ANKLE]);
  const order: Side[] = score("RIGHT") > score("LEFT") ? ["RIGHT", "LEFT"] : ["LEFT", "RIGHT"];
  for (const side of order) {
    const c = calibrationFromLandmarks(landmarks, side);
    if (c) return { side, ...c };
  }
  return null;
}
