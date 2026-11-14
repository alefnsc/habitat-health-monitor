import { calibrationOfBestSide, type Landmark } from "../../vendor/ground-truth/demo/src/pose/landmarks";
import { scaleFrom } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { COPY } from "./copy";

export type CalResult =
  | { ok: true; metersPerUnit: number; method: "known_length" | "stature"; note: string | null }
  | { ok: false; error: string };

// Only the y values reach the vendored helper: the scale is metres per frame height, so a diagonal is not used.
export function calibrateKnownLength(a: { x: number; y: number }, b: { x: number; y: number }, lengthM: number): CalResult {
  const r = scaleFrom({ kind: "known-length", lengthM, yA: a.y, yB: b.y });
  return r.ok ? { ok: true, metersPerUnit: r.metersPerUnit, method: "known_length", note: null } : { ok: false, error: r.reason };
}

export function calibrateStature(statureM: number, landmarks: readonly Landmark[] | undefined): CalResult {
  if (!landmarks) return { ok: false, error: COPY["calib.noPose"] };
  const c = calibrationOfBestSide(landmarks);
  if (!c) return { ok: false, error: COPY["calib.standInFrame"] };
  const r = scaleFrom({ kind: "stature", statureM, eyeY: c.eyeY, ankleY: c.ankleY });
  return r.ok
    ? { ok: true, metersPerUnit: r.metersPerUnit, method: "stature", note: COPY["calib.statureNote"] }
    : { ok: false, error: r.reason };
}
