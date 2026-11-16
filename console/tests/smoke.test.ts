import { describe, expect, test } from "vitest";
import { SCREENS, screenFromHash } from "../src/main";

describe("scaffold", () => {
  test("test_screens_list", () => {
    expect([...SCREENS]).toEqual(["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "signals", "prompts", "body"]);
  });
  test("test_default_screen", () => {
    expect(screenFromHash("")).toBe("panel");
    expect(screenFromHash("#/nasa")).toBe("nasa");
    expect(screenFromHash("#/nope")).toBe("panel");
  });
});
