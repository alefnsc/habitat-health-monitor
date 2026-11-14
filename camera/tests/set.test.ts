import { describe, expect, test } from "vitest";
import { createSetState } from "../src/set";

describe("set", () => {
  test("test_second_set_keeps_scale", () => {
    const s = createSetState();
    expect(s.nextSet()).toEqual({ needsCalibration: true, metersPerUnit: null });
    s.setScale(1.0);
    expect(s.nextSet()).toEqual({ needsCalibration: false, metersPerUnit: 1.0 });
  });
});
