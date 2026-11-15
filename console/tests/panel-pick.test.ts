import { describe, expect, test } from "vitest";
import type { Session } from "../src/contract";
import { laneCrew, pickSession } from "../src/model/panel/pick";

const s = (id: string, camera_reps: number): Session =>
  ({ session: id, mass_kg: 10, g: 9.81, crew: null, started_at: "2026-11-15T16:00:00Z", ended_at: null, exercise: "curl", camera_reps } as unknown as Session);

describe("panel: which camera session the lift cards show (E2)", () => {
  test("the newest session with camera reps, not a newer empty one", () => {
    // Newest first, as GET /api/sessions returns them: a set in progress or a refused set has no reps yet.
    expect(pickSession([s("s-3", 0), s("s-2", 4), s("s-1", 6)])?.session).toBe("s-2");
  });
  test("falls back to the newest session when none has reps", () => {
    expect(pickSession([s("s-2", 0), s("s-1", 0)])?.session).toBe("s-2");
  });
  test("no sessions gives null", () => {
    expect(pickSession([])).toBeNull();
  });
});

describe("panel: which lanes follow the crew selector (E3)", () => {
  test("cabin lanes carry no crew, so they ignore the selector", () => {
    for (const ind of ["cabin_temp", "cabin_rh", "cabin_ppco2"]) expect(laneCrew(ind, "crew-a")).toBeUndefined();
  });
  test("body lanes follow the selected crew", () => {
    for (const ind of ["hr", "spo2", "sleep_h"]) expect(laneCrew(ind, "crew-b")).toBe("crew-b");
  });
  test("all crews stays all crews", () => {
    expect(laneCrew("hr", undefined)).toBeUndefined();
  });
});
