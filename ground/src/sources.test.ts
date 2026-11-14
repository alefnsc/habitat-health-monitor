// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emptyView, reduce } from "./model";
import { render } from "./render";
import { liveSource } from "./sources";
import type { Arrival } from "./types";

const mk = (id: number): Arrival => ({ arrival_id: id, received_at: "z", beacon: null, items: [] });
const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => mk(a + i));
const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body)));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("liveSource", () => {
  it("live_pages_until_caught_up", async () => {
    const urls: string[] = [];
    const pages = [range(1, 1000), range(1001, 1003), [], []];
    const fetchFn = vi.fn((u: string) => {
      urls.push(u);
      return ok(pages.shift() ?? []);
    }) as unknown as typeof fetch;
    const got: number[] = [];
    const s = liveSource("", (a) => got.push(a.arrival_id), fetchFn);
    await vi.advanceTimersByTimeAsync(10);
    expect(got.length).toBe(1003);
    expect(got).toEqual([...got].sort((a, b) => a - b));
    expect(urls).toEqual([
      "/ground/arrivals?after=0&limit=1000",
      "/ground/arrivals?after=1000&limit=1000",
      "/ground/arrivals?after=1003&limit=1000",
    ]);
    await vi.advanceTimersByTimeAsync(980);
    expect(urls.length).toBe(3);
    await vi.advanceTimersByTimeAsync(30);
    expect(urls.length).toBe(4);
    expect(urls[3]).toContain("after=1003");
    s.stop();
  });

  it("live_survives_fetch_error", async () => {
    let n = 0;
    const fetchFn = vi.fn(() => {
      n += 1;
      if (n === 1) return Promise.reject(new Error("down"));
      return ok(n === 2 ? [mk(1)] : []);
    }) as unknown as typeof fetch;
    const got: number[] = [];
    const s = liveSource("", (a) => got.push(a.arrival_id), fetchFn);
    await vi.advanceTimersByTimeAsync(10);
    expect(got).toEqual([]);
    await vi.advanceTimersByTimeAsync(1100);
    expect(got).toEqual([1]);
    s.stop();
  });
});

describe("render", () => {
  it("render_smoke", () => {
    const beacon = {
      link: { state: "contact", light_time_s: 720, time_scale: 60, queue_len: 4, last_blackout: null },
      hold_s: 12, in_flight: 0, fetched_id: 0, delivered_id: 0, last_blackout_cause: null, sent_at: "z",
    } as unknown as Arrival["beacon"];
    const items = [
      { id: 1, kind: "reading" as const, created_at: "z", payload: { ind: "hr", val: 72, unit: "bpm", src: "hobby", q: ["ok"], crew: "crew-a", status: "ok", rule_id: null, source_kind: "team_convention", measured_at: "2026-11-15T13:00:05.000Z" } },
      { id: 2, kind: "alert" as const, created_at: "z", payload: { id: "a1", ind: "cabin_co2", status: "watch", prev_status: "ok", rule_id: "co2_1h", measured_at: "2026-11-15T13:00:06.000Z", crew: null, escalate_to: "cmo" } },
    ];
    const view = reduce(emptyView(), { arrival_id: 1, received_at: "z", beacon, items }, 1000);
    const root = document.createElement("div");
    render(root, view, 1000, null);
    const t = root.textContent!.replace(/\s+/g, " ");
    for (const s of [
      "Earth's view, as of T − 12 min 00 s", "72 bpm", "hobby", "Team convention, not clinical",
      "Queue on the habitat: 4 (as last reported)", "No blackout yet", "ok → watch", "cmo",
    ]) expect(t).toContain(s);
  });
});
