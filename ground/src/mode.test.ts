import { describe, expect, it } from "vitest";
import { LIVE_BANNER, STALE_MS, decideMode, fetchSummary } from "./mode";

const now = Date.parse("2026-11-14T15:10:00.000Z");

describe("decideMode", () => {
  it("is replay with no summary or no arrival", () => {
    expect(decideMode(null, now)).toBe("replay");
    expect(decideMode({ last_arrival_at: null }, now)).toBe("replay");
    expect(decideMode({ last_arrival_at: "nonsense" }, now)).toBe("replay");
  });
  it("is live within 5 minutes and replay after", () => {
    expect(decideMode({ last_arrival_at: new Date(now - STALE_MS).toISOString() }, now)).toBe("live");
    expect(decideMode({ last_arrival_at: new Date(now - STALE_MS - 1).toISOString() }, now)).toBe("replay");
  });
});

describe("fetchSummary", () => {
  it("returns null on errors and non-OK", async () => {
    const bad = (async () => new Response("x", { status: 500 })) as typeof fetch;
    const boom = (async () => { throw new Error("down"); }) as typeof fetch;
    expect(await fetchSummary("", bad)).toBeNull();
    expect(await fetchSummary("", boom)).toBeNull();
  });
  it("parses the summary", async () => {
    const ok = (async (u: string) => {
      expect(u).toBe("/ground/summary");
      return new Response(JSON.stringify({ last_arrival_at: "2026-11-14T15:00:00.000Z" }));
    }) as unknown as typeof fetch;
    expect(await fetchSummary("", ok)).toEqual({ last_arrival_at: "2026-11-14T15:00:00.000Z" });
  });
});

it("live banner says synthetic crew data is labelled", () => {
  expect(LIVE_BANNER).toMatch(/sim-1/);
  expect(LIVE_BANNER).toMatch(/synthetic/i);
});
