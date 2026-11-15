import { describe, expect, test } from "vitest";
import { addTap, parseCrew } from "../src/controls";

describe("calibration taps (E5)", () => {
  test("the first two taps make the pair", () => {
    expect(addTap([], { x: 0.1, y: 0.2 })).toEqual([{ x: 0.1, y: 0.2 }]);
    expect(addTap([{ x: 0.1, y: 0.2 }], { x: 0.1, y: 0.6 })).toEqual([{ x: 0.1, y: 0.2 }, { x: 0.1, y: 0.6 }]);
  });
  test("a third tap starts the pair over instead of being ignored", () => {
    expect(addTap([{ x: 0.1, y: 0.2 }, { x: 0.1, y: 0.6 }], { x: 0.5, y: 0.5 })).toEqual([{ x: 0.5, y: 0.5 }]);
  });
  test("the input array is not changed", () => {
    const taps = [{ x: 0.1, y: 0.2 }];
    addTap(taps, { x: 0.3, y: 0.4 });
    expect(taps).toHaveLength(1);
  });
});

describe("crew pick (E4)", () => {
  test("a listed crew is accepted", () => {
    expect(parseCrew("crew-a")).toBe("crew-a");
    expect(parseCrew("crew-c")).toBe("crew-c");
  });
  test("no pick or an unknown value is no crew: a forgotten choice must not label the set", () => {
    expect(parseCrew("")).toBeNull();
    expect(parseCrew("crew-z")).toBeNull();
  });
});
