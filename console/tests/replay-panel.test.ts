// @vitest-environment jsdom
import { afterEach, describe, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import sample from "./fixtures/ground-replay.sample.json";
import { parseReplayFile, statusAt, type ReplayFile } from "../src/replay/adapt";
import {
  alertsBetween, parseExerciseReplay, readingsUntil, recordedSpan, replaySource,
} from "../src/replay/panel";
import { renderPanel } from "../src/views/panel";
import { copyFor, liveSource, type PanelSource } from "../src/views/panel/source";

// uPlot draws on a canvas, which jsdom does not have: the mount test only checks the text around the charts.
vi.mock("uplot", () => ({
  default: class {
    static tzDate(d: Date) {
      return d;
    }
    destroy() {}
  },
}));

const file = (): ReplayFile => parseReplayFile(JSON.parse(JSON.stringify(sample)));
const T0 = Date.parse("2026-11-15T12:00:00Z");
const EXERCISE_FILE = readFileSync(join(__dirname, "..", "..", "data", "replay", "exercise-day.jsonl"), "utf8");

describe("exercise replay set", () => {
  test("one session of 8 camera reps, each placed at start + its end time", () => {
    const set = parseExerciseReplay(EXERCISE_FILE, T0)!;
    expect(set.session).toMatchObject({
      session: "demo-ex-1", mass_kg: 10, g: 9.81, crew: null, exercise: null, camera_reps: 8, load_cell_reps: 0,
      started_at: "2026-11-15T12:00:00.000Z",
    });
    expect(set.reps).toHaveLength(8);
    expect(set.reps[0]).toMatchObject({ rep: 1, src: "camera", work_j: 40.2, measured_at: "2026-11-15T12:00:05.800Z" });
    expect(set.reps.reduce((s, r) => s + r.work_j, 0)).toBeCloseTo(320.2, 6);
    expect(set.session.ended_at).toBe(set.reps[7].measured_at);
  });

  test("no rep lines gives no set", () => {
    expect(parseExerciseReplay("", T0)).toBeNull();
    expect(parseExerciseReplay('{"t_ms":0,"kind":"reading","msg":{}}\nnot json\n', T0)).toBeNull();
  });
});

describe("replay readings at habitat time", () => {
  test("recorded span runs from the first to the last reading", () => {
    expect(recordedSpan(file())).toEqual([T0, T0 + 9000]);
  });

  test("readings are those measured by the replay clock, oldest first", () => {
    const f = file();
    expect(readingsUntil(f, "hr", 0, T0 + 4999).map((r) => r.val)).toEqual([70]);
    expect(readingsUntil(f, "hr", 0, T0 + 5000).map((r) => r.val)).toEqual([70, 74]);
    expect(readingsUntil(f, "hr", T0 + 1, T0 + 9000).map((r) => r.val)).toEqual([74]);
    expect(readingsUntil(f, "hr", T0 + 5000, T0 + 5000).map((r) => r.val)).toEqual([74]); // both ends inclusive
    expect(readingsUntil(f, "spo2", 0, T0 + 9000)).toEqual([]);
    const r = readingsUntil(f, "cabin_ppco2", 0, T0 + 9000)[0];
    expect(r).toMatchObject({ src: "replay", dev: "BME280", node: "sim-1", q: ["ok"], measured_at: "2026-11-15T12:00:09Z" });
  });

  test("status holds the newest reading per indicator, at the replay clock", () => {
    const s = statusAt(file(), 9000, null);
    expect(Object.fromEntries(s.results.map((e) => [e.ind, e.val]))).toEqual({ hr: 74, cabin_ppco2: 3.1 });
    expect(s.generated_at).toBe("2026-11-15T12:00:09.000Z");
  });

  test("the status board and the panel share one time base: the measured time", async () => {
    // hr 74 was measured at 12:00:05 but arrives only with the 9 s batch.
    const f = file();
    f.arrivals[2].items.push(f.arrivals[1].items.splice(0, 1)[0]);
    expect(statusAt(f, 5000, null).results.find((e) => e.ind === "hr")!.val).toBe(74);
    expect((await replaySource(f, null, () => 5000).status()).results).toEqual(statusAt(f, 5000, null).results);
  });

  test("alerts fire once, at their measured time (arrival time when the file has none)", () => {
    const f = file();
    f.arrivals[1].items.push({ id: 9, kind: "alert", created_at: "x", payload: {
      id: 9, ind: "cabin_temp", status: "watch", prev_status: "ok", rule_id: "cabin_performance_temp",
      measured_at: "2026-11-15T12:00:03Z", crew: null, escalate_to: "cmo" } });
    expect(alertsBetween(f, T0, T0 + 2999)).toEqual([]);
    expect(alertsBetween(f, T0, T0 + 3000).map((a) => a.ind)).toEqual(["cabin_temp"]);
    expect(alertsBetween(f, T0 + 3000, T0 + 8999)).toEqual([]);
    expect(alertsBetween(f, T0 + 3000, T0 + 9000).map((a) => a.ind)).toEqual(["hr"]);
  });
});

describe("replay panel source", () => {
  const src = (positionMs: number) => {
    const set = parseExerciseReplay(EXERCISE_FILE, T0 - 60_000);
    return replaySource(file(), set, () => positionMs);
  };

  test("it labels its values as a replay and runs on the replay clock", () => {
    const s = src(5000);
    expect(s.label).toBe("Replay (recorded)");
    expect(s.now()).toBe(T0 + 5000);
    expect(s.laneWindow!(0)).toEqual([T0 / 1000, (T0 + 9000) / 1000]);
    expect(liveSource.label).toBeUndefined();
  });

  test("the source carries its own wording; the live source keeps the hub wording", () => {
    const s = src(0);
    expect(copyFor(s, "panel.noData")).toBe("Not available in the replay.");
    expect(copyFor(s, "panel.massNone")).toBe("No weigh-ins in this replay.");
    expect(copyFor(s, "panel.window")).toBe("Recorded session");
    expect(copyFor(s, "panel.notOnBench")).toBe("Not in this replay:");
    expect(copyFor(s, "panel.lift")).toBe("Lift");
    expect(copyFor(liveSource, "panel.noData")).toBe("No data");
    expect(s.setNote).toBe("Synthetic set from the exercise replay file, shown one minute before the cabin recording.");
    expect(replaySource(file(), null, () => 0).setNote).toBeUndefined();
  });

  test("lift and training work come from the replay set", async () => {
    const s = src(0);
    const sessions = await s.sessions();
    expect(sessions.map((x) => x.session)).toEqual(["demo-ex-1"]);
    const reps = await s.reps("demo-ex-1");
    expect(reps.pairs.map((p) => p.camera!.rep)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(reps.pairs.every((p) => p.load_cell === null)).toBe(true);
    const day = await s.exerciseDay();
    expect(day).toMatchObject({ sessions: 1, camera_reps: 8, replay: true, cell_work_j: null });
    expect(day.camera_work_j).toBeCloseTo(320.2, 6);
  });

  test("with no exercise replay, the lift has no set", async () => {
    const s = replaySource(file(), null, () => 0);
    expect(await s.sessions()).toEqual([]);
    expect((await s.exerciseDay()).camera_work_j).toBeNull();
  });

  test("link state comes from the replay beacons", async () => {
    expect((await src(0).link()).state).toBe("contact");
    expect((await src(5000).link()).state).toBe("blackout");
  });

  test("the replay source has no signals, so the panel shows no signals chip", () => {
    expect("signals" in replaySource(file(), null, () => 0)).toBe(false);
    expect("signals" in src(0)).toBe(false);
  });

  test("feeds the replay does not carry are refused, so their cards say so", async () => {
    const s = src(0);
    for (const p of [s.spaceWeather(), s.issCabin(), s.issReference(), s.foodDay()]) await expect(p).rejects.toThrow();
  });
});

describe("panel refresh", () => {
  afterEach(() => vi.useRealTimers());

  test("a frozen source clock (a paused replay) does not reload or redraw the cards", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
    let clock = T0;
    const calls = { status: 0, readings: 0 };
    const no = () => Promise.reject(new Error("none"));
    const stub: PanelSource = {
      now: () => clock, refreshMs: 1000, lanesRefreshMs: 5000, laneWindow: () => [T0 / 1000, T0 / 1000 + 60],
      status: async () => (calls.status++, { crew: null, generated_at: "", nodes: [], results: [] }),
      sessions: async () => [], reps: no, readings: async () => (calls.readings++, []),
      foodDay: no, exerciseDay: no, spaceWeather: no, issCabin: no, issReference: no, link: no,
    };
    document.body.innerHTML = '<div id="p"></div>';
    const dispose = renderPanel(document.getElementById("p")!, stub);
    await vi.advanceTimersByTimeAsync(0);
    expect(calls).toEqual({ status: 1, readings: 7 }); // 6 lanes + weigh-ins
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual({ status: 1, readings: 7 }); // clock frozen, lanes current: nothing to do
    clock += 500;
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual({ status: 2, readings: 8 }); // moved: cards reload, lanes not due yet
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual({ status: 3, readings: 15 }); // frozen again: the lanes catch up to the paused frame once
    await vi.advanceTimersByTimeAsync(3000);
    expect(calls).toEqual({ status: 3, readings: 15 });
    dispose();
  });
});

describe("replay mode opens on the habitat panel", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function mount(exercise: Response) {
    const { mountReplayApp } = await import("../src/replay/app");
    const urls: string[] = [];
    const ws = vi.fn();
    vi.stubGlobal("WebSocket", ws);
    // The sample plus one cabin reading at t0, so the cabin chip has a reading from the first frame.
    const rec = JSON.parse(JSON.stringify(sample)) as ReplayFile;
    rec.arrivals[0].items.push({ id: 10, kind: "reading", created_at: "2026-11-15T12:00:00Z", payload: {
      ...rec.arrivals[0].items[0].payload, id: 10, ind: "cabin_temp", val: 22, unit: "C", src: "replay", dev: "BME280",
      status: "ok", rule_id: "cabin_health_box_temp", source_kind: "nasa_std" } });
    const fetchImpl = vi.fn(async (u: string) => {
      urls.push(u);
      return u.endsWith("replay.json") ? new Response(JSON.stringify(rec)) : exercise;
    });
    vi.stubGlobal("fetch", fetchImpl);
    location.hash = "";
    document.body.innerHTML = '<div id="app"></div>';
    const root = document.getElementById("app")!;
    await mountReplayApp(root, { base: "./", fetchImpl });
    return { root, urls, ws };
  }

  test("panel cards read the replay, the banner stays and nothing claims to be live", async () => {
    const { root, urls, ws } = await mount(new Response(EXERCISE_FILE));
    await vi.waitFor(() => expect(root.querySelector(".p-lift .bars")).not.toBeNull());

    expect(root.querySelector(".panel")).not.toBeNull();
    expect(root.textContent).toContain("Replay of a recorded session — not live data.");
    expect(root.querySelector('nav [aria-current="page"]')!.textContent).toBe("Habitat panel");
    const top = root.querySelector(".p-top")!.textContent!;
    expect(top).toContain("Cabin sensors Replay (recorded)");
    expect(top).not.toMatch(/\blive\b/);
    expect(top).not.toContain("Signals");
    expect(root.querySelector('.p-top a[href="#/signals"]')).toBeNull();
    expect(root.querySelector(".p-lift")!.textContent).toContain("Synthetic set from the exercise replay file");
    expect(root.querySelectorAll(".p-lift .bar")).toHaveLength(8);
    expect(root.querySelector(".p-vitals")!.textContent).toContain("Recorded session");
    expect(root.querySelector(".p-vitals")!.textContent).not.toContain("Last 6 hours");
    expect(root.querySelector(".p-vitals")!.textContent).toContain("Not in this replay:");
    expect(root.querySelector(".p-mass")!.textContent).toContain("No weigh-ins in this replay.");
    expect(root.querySelector(".p-rad")!.textContent).toContain("Not available in the replay.");

    expect(urls).toEqual(["./replay.json", "./exercise-day.jsonl"]);
    expect(ws).not.toHaveBeenCalled();
  });

  test("without the exercise replay the lift cards keep their empty text", async () => {
    const { root } = await mount(new Response("", { status: 404 }));
    await vi.waitFor(() => expect(root.querySelector(".p-vitals .vlane")).not.toBeNull());
    expect(root.querySelector(".p-lift")!.textContent).toContain("No set yet.");
    expect(root.querySelector(".p-places")!.textContent).toContain("No set yet.");
  });
});
