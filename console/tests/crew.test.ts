import { describe, expect, test, vi } from "vitest";
import { ApiError } from "../src/api";
import { loadCrew, onCrewChange, saveCrew, setCurrentCrew, setWearer } from "../src/crew";

class MemStorage {
  m = new Map<string, string>();
  getItem(k: string) { return this.m.get(k) ?? null; }
  setItem(k: string, v: string) { this.m.set(k, v); }
  removeItem(k: string) { this.m.delete(k); }
}
const mem = () => new MemStorage() as unknown as Storage;

describe("crew", () => {
  test("test_load_default", () => {
    expect(loadCrew(mem())).toBeNull();
  });

  test("test_round_trip", () => {
    const s = mem();
    saveCrew(s, "crew-b");
    expect(loadCrew(s)).toBe("crew-b");
    expect((s as unknown as MemStorage).m.has("habitat.crew")).toBe(true);
  });

  test("test_storage_throws", () => {
    const bad = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    } as unknown as Storage;
    expect(loadCrew(bad)).toBeNull();
    expect(() => saveCrew(bad, "crew-a")).not.toThrow();
  });

  test("test_invalid_value", () => {
    const s = mem();
    s.setItem("habitat.crew", "crew-z");
    expect(loadCrew(s)).toBeNull();
  });

  test("test_change_event", () => {
    const cb = vi.fn();
    const off = onCrewChange(cb);
    setCurrentCrew("crew-a");
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith("crew-a");
    off();
    setCurrentCrew("crew-b");
    expect(cb).toHaveBeenCalledTimes(1);
  });

  test("test_set_wearer", async () => {
    const post = vi.fn().mockResolvedValue(undefined);
    await expect(setWearer("vitals-1", "crew-b", post)).resolves.toEqual({ ok: true });
    expect(post).toHaveBeenCalledWith("vitals-1", "crew-b");
    const bad = vi.fn().mockRejectedValue(new ApiError(422, "HTTP 422: bad_crew"));
    await expect(setWearer("vitals-1", "crew-b", bad)).resolves.toEqual({
      ok: false, error: "Could not set the wearer: HTTP 422: bad_crew",
    });
  });
});
