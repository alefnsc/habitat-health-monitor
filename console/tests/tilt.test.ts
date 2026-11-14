import { describe, expect, test } from "vitest";
import { formatValue } from "../src/format";
import { UNITS } from "../src/payload";

describe("tilt (D39)", () => {
  test("test_tilt_unit_and_format", () => {
    expect(UNITS.tilt).toBe("state");
    expect(formatValue("tilt", 1, "state")).toBe("1 state");
    expect(formatValue("tilt", 0, "state")).toBe("0 state");
  });
});
