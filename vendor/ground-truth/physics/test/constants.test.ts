import { describe, expect, it } from "vitest";
import { G_ENV_MS2, STANDARD_GRAVITY_MS2, GENC_2010_PEAK_LOAD_DECREMENT, type Body } from "../src/index";

describe("constants", () => {
  it("carries the brief's gravity table", () => {
    expect(G_ENV_MS2.EARTH).toBe(9.81);
    expect(G_ENV_MS2.MARS).toBe(3.71);
    expect(G_ENV_MS2.MOON).toBe(1.62);
    expect(G_ENV_MS2.ISS).toBe(0);
    expect(G_ENV_MS2.TRANSIT).toBe(0);
    expect(STANDARD_GRAVITY_MS2).toBe(9.81);
  });

  it("has a gravity for every Body, so G_ENV_MS2[env.body] typechecks", () => {
    const bodies: Body[] = ["EARTH", "MOON", "MARS", "ISS", "TRANSIT"];
    for (const body of bodies) {
      expect(G_ENV_MS2[body]).toBeTypeOf("number");
    }
    expect(Object.keys(G_ENV_MS2).sort()).toEqual([...bodies].sort());
  });

  it("carries Genc 2010's on-orbit peak-load decrements", () => {
    expect(GENC_2010_PEAK_LOAD_DECREMENT).toEqual({ running: 0.75, walking: 0.77, squat: 0.65 });
  });
});
