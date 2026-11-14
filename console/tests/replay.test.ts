// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import sample from "./fixtures/ground-replay.sample.json";
import { linkAt, parseReplayFile, statusAt } from "../src/replay/adapt";
import { createReplayPlayer, replayBanner } from "../src/replay/player";
import { mountReplayApp } from "../src/replay/app";
import { escalationSteps } from "../src/model/guidance";

const file = () => parseReplayFile(JSON.parse(JSON.stringify(sample)));

describe("replay adapt", () => {
  test("test_parse_rejects", () => {
    expect(() => parseReplayFile({ ...sample, kind: "other" })).toThrow("Replay file not recognised");
    expect(() => parseReplayFile({ ...sample, v: 2 })).toThrow("Replay file not recognised");
    expect(parseReplayFile(sample).label).toContain("São Paulo");
  });

  test("test_status_at_schedule", () => {
    const f = file();
    const at = (p: number) => Object.fromEntries(statusAt(f, p, null).results.map((e) => [e.ind, e.val]));
    expect(at(4999)).toEqual({ hr: 70 });
    expect(at(5000)).toEqual({ hr: 74 });
    expect(at(9000)).toEqual({ hr: 74, cabin_ppco2: 3.1 });
    expect(statusAt(f, 5000, null).generated_at).toBe("2026-11-15T12:00:05.000Z");
  });

  test("test_status_entry_fields", () => {
    const hr = statusAt(file(), 5000, null).results.find((e) => e.ind === "hr")!;
    expect(hr).toMatchObject({ src: "hobby", dev: "MAX30102", q: ["motion"], status: "unknown", rule_id: null, guidance_id: null });
    const co2 = statusAt(file(), 9000, null).results.find((e) => e.ind === "cabin_ppco2")!;
    expect(co2.guidance_id).toBe("co2_1h.watch");
  });

  test("test_non_reading_items_ignored", () => {
    expect(statusAt(file(), 9000, null).results.map((e) => e.ind).sort()).toEqual(["cabin_ppco2", "hr"]);
  });

  test("test_link_at", () => {
    const f = file();
    expect(linkAt(f, 4999)?.state).toBe("contact");
    expect(linkAt(f, 5000)?.state).toBe("blackout");
    const early = file();
    early.arrivals[0].beacon = null;
    expect(linkAt(early, 100)).toBeNull();
  });

  test("test_light_time_from_replay", () => {
    const link = linkAt(file(), 0)!;
    expect(escalationSteps({ status: "act", escalate_to: "flight_surgeon" }, link)[2].text).toContain("12 min one-way (demo: 12 s)");
  });
});

describe("replay player", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("test_loop", () => {
    let now = 0;
    const p = createReplayPlayer(file(), () => now, () => {});
    p.play();
    now = 12000;
    expect(p.positionMs()).toBe(0);
    expect(statusAt(file(), p.positionMs(), null).results.map((e) => e.val)).toEqual([70]);
    p.pause();
  });

  test("test_pause_restart", () => {
    let now = 0;
    const p = createReplayPlayer(file(), () => now, () => {});
    p.play();
    now = 2000;
    p.pause();
    now = 8000;
    expect(p.positionMs()).toBe(2000);
    p.restart();
    expect(p.positionMs()).toBe(0);
  });

  test("test_banner", () => {
    const t = replayBanner("Recorded session, 2026-11-15, São Paulo", 9000, 9000);
    expect(t).toContain("Replay of a recorded session — not live data. Recorded session, 2026-11-15, São Paulo");
    expect(t).toContain("00:09 / 00:09");
  });
});

describe("replay mode", () => {
  test("test_no_network and test_unavailable_screens", async () => {
    const urls: string[] = [];
    const ws = vi.fn();
    vi.stubGlobal("WebSocket", ws);
    const fetchImpl = vi.fn(async (u: string) => (urls.push(u), new Response(JSON.stringify(sample))));
    vi.stubGlobal("fetch", fetchImpl);
    document.body.innerHTML = '<div id="app"></div>';
    const root = document.getElementById("app")!;
    await mountReplayApp(root, { base: "/habitat-health-monitor/console/", fetchImpl });
    expect(urls).toEqual(["/habitat-health-monitor/console/replay.json"]);
    expect(root.textContent).toContain("Replay of a recorded session");
    expect(root.querySelector('[data-tile="hr"]')).not.toBeNull();
    for (const s of ["entry", "history", "exercise", "food", "nasa", "prompts", "body"]) {
      location.hash = `#/${s}`;
      window.dispatchEvent(new Event("hashchange"));
      expect(root.querySelector("#screen")!.textContent).toBe("Not available in the replay.");
    }
    expect(urls).toHaveLength(1);
    expect(ws).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
