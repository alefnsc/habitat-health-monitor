import { describe, expect, test } from "vitest";
import { calibrateKnownLength, calibrateStature } from "../src/calibrate";
import { COPY } from "../src/copy";
import { LANDMARK, type Landmark } from "../../vendor/ground-truth/demo/src/pose/landmarks";

function pose(eyeY: number, ankleY: number): Landmark[] {
  const l: Landmark[] = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, z: 0, visibility: 1 }) as Landmark);
  for (const i of [LANDMARK.LEFT_EYE, LANDMARK.RIGHT_EYE]) l[i] = { ...l[i], y: eyeY };
  for (const i of [LANDMARK.LEFT_ANKLE, LANDMARK.RIGHT_ANKLE]) l[i] = { ...l[i], y: ankleY };
  return l;
}

describe("calibrate", () => {
  test("test_known_length_known", () => {
    const r = calibrateKnownLength({ x: 0.4, y: 0.3 }, { x: 0.4, y: 0.6 }, 0.3);
    expect(r).toMatchObject({ ok: true, method: "known_length", note: null });
    expect(r.ok && r.metersPerUnit).toBeCloseTo(1.0, 6);
  });

  test("test_known_length_diagonal", () => {
    const r = calibrateKnownLength({ x: 0.3, y: 0.3 }, { x: 0.6, y: 0.6 }, 0.3);
    expect(r.ok && r.metersPerUnit).toBeCloseTo(1.0, 6);
  });

  test("test_calibrate_too_small", () => {
    const r = calibrateKnownLength({ x: 0.4, y: 0.3 }, { x: 0.4, y: 0.33 }, 0.3);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("at least 5 % of the frame height");
  });

  test("test_stature_numbers", () => {
    const r = calibrateStature(1.75, pose(0.15, 0.85));
    expect(r).toMatchObject({ ok: true, method: "stature" });
    expect(r.ok && r.metersPerUnit).toBeCloseTo((0.897 * 1.75) / 0.7, 3);
  });

  test("test_stature_label", () => {
    const r = calibrateStature(1.75, pose(0.15, 0.85));
    expect(r.ok && r.note).toBe("Height method uses an unchecked body proportion (0.897); a known length is preferred.");
    expect(COPY["calib.statureNote"]).toBe(r.ok ? r.note : "");
  });

  test("test_stature_rejects", () => {
    for (const [eye, ankle] of [[0.8, 0.2], [0.3, 0.49]] as const) {
      const r = calibrateStature(1.75, pose(eye, ankle));
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.error).toMatch(/stand/i);
    }
    expect(calibrateStature(1.75, undefined).ok).toBe(false);
  });
});
