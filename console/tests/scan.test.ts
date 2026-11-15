import { describe, expect, test } from "vitest";
import { firstKnownCode, parsePackCode } from "../src/model/scan";

const cat = { items: [{ id: "white-rice-dry" }, { id: "bar" }] };

describe("pack codes (D44)", () => {
  test("a pack code names a catalogue food", () => {
    expect(parsePackCode("hhm-food:white-rice-dry", cat)).toBe("white-rice-dry");
  });

  test("whitespace around a typed or scanned code is ignored", () => {
    expect(parsePackCode("  hhm-food:bar\n", cat)).toBe("bar");
  });

  test("a food that is not in the catalogue is refused", () => {
    expect(parsePackCode("hhm-food:nope", cat)).toBeNull();
  });

  test("a code from elsewhere is refused", () => {
    expect(parsePackCode("https://example.org/bar", cat)).toBeNull();
    expect(parsePackCode("bar", cat)).toBeNull();
    expect(parsePackCode("HHM-FOOD:bar", cat)).toBeNull();
    expect(parsePackCode("hhm-food:", cat)).toBeNull();
    expect(parsePackCode("", cat)).toBeNull();
  });

  test("of several codes in one frame, the first catalogue food wins", () => {
    expect(firstKnownCode(["https://example.org", "hhm-food:nope", "hhm-food:bar", "hhm-food:white-rice-dry"], cat)).toBe("bar");
    expect(firstKnownCode(["hhm-food:nope"], cat)).toBeNull();
    expect(firstKnownCode([], cat)).toBeNull();
  });
});
