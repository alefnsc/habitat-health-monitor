// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { emptyView, reduce } from "./model";
import { loadReplay, parseReplay, positionLabel, replayBanner, replaySource } from "./replay";
import { render, renderCrewView } from "./render";
import type { Arrival, ReplayFile } from "./types";

const FILE: ReplayFile = {
  v: 1, kind: "ground-replay", label: "Recorded session, 2026-11-15, São Paulo",
  exported_at: "z", t0: "2026-11-15T13:00:00.000Z", light_time_s: 720, time_scale: 60,
  arrivals: [0, 5000, 9000].map((at_ms) => ({ at_ms, beacon: null, items: [] })),
};

function rig() {
  let now = 0;
  const got: Arrival[] = [];
  const reset = vi.fn();
  const src = replaySource(FILE, (a) => got.push(a), reset, () => now);
  return { src, got, reset, at: (t: number) => { now = t; src.tick(); } };
}

describe("replaySource", () => {
  it("schedule", () => {
    const r = rig();
    r.at(0); expect(r.got.length).toBe(1);
    r.at(4999); expect(r.got.length).toBe(1);
    r.at(5000); expect(r.got.length).toBe(2);
    r.at(9000); expect(r.got.length).toBe(3);
  });
  it("loop", () => {
    const r = rig();
    r.at(9000);
    r.at(12000);
    expect(r.reset).toHaveBeenCalledTimes(1);
    expect(r.got.length).toBe(4);
    expect(r.got[3].arrival_id).toBe(1);
  });
  it("pause", () => {
    const r = rig();
    r.at(2000);
    r.src.pause();
    r.at(8000);
    expect(r.src.positionMs()).toBe(2000);
    expect(r.got.length).toBe(1);
  });
  it("wrong_kind", async () => {
    expect(() => parseReplay({ ...FILE, kind: "other" })).toThrow();
    const f = (async () => new Response(JSON.stringify({ kind: "other" }))) as unknown as typeof fetch;
    expect(await loadReplay("/x", f)).toEqual({ message: "Replay file not recognised" });
    const nf = (async () => new Response("", { status: 404 })) as unknown as typeof fetch;
    expect(await loadReplay("/x", nf)).toEqual({ message: "Replay data not yet published" });
  });
  it("banner", () => {
    const root = document.createElement("div");
    render(root, emptyView(), Date.parse(FILE.t0), replayBanner(FILE.label));
    expect(root.textContent).toContain(
      "Replay of a recorded session — not live data. Recorded session, 2026-11-15, São Paulo");
    expect(positionLabel(9000, 9000)).toBe("00:09 / 00:09");
  });
});

describe("crew view", () => {
  const items = ["watch", "ok"].map((status, i) => ({
    id: i + 1, kind: "reading" as const, created_at: "z",
    payload: { ind: i ? "hr" : "cabin_co2", val: 1800, unit: "ppm", src: "hobby", q: ["ok"], crew: null,
      status, rule_id: i ? "hr_rest" : "co2_1h", source_kind: null, measured_at: "2026-11-15T13:00:05.000Z" },
  }));
  const view = reduce(emptyView(), { arrival_id: 1, received_at: "z", beacon: null, items }, 0);
  it("crew_view_fallback", () => {
    const root = document.createElement("div");
    renderCrewView(root, view, [
      { id: "co2_1h.watch", do_now: "Open a vent and re-check.", tell: "Tell the crew lead." },
      { id: "hr_rest.ok", do_now: "SHOULD NOT SHOW" },
    ]);
    const t = root.textContent!;
    expect(t).toContain("watch");
    expect(t).toContain("Open a vent and re-check.");
    expect(t).not.toContain("SHOULD NOT SHOW");
  });
});
