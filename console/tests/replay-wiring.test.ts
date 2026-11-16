// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import sample from "./fixtures/ground-replay.sample.json";
import { mountReplayApp } from "../src/replay/app";
import { hubEvents } from "../src/state";

// uPlot needs a canvas and matchMedia, which jsdom does not have.
vi.mock("uplot", () => ({ default: class { static tzDate(d: Date) { return d; } destroy() {} } }));

// The sample: beacons "contact" at 0 and "blackout" at 5000; one alert with no measured time, so it counts at its
// arrival, 9000. The player loops every 9000 + 3000 ms and emits a frame every 500 ms.
const replayJson = () => new Response(JSON.stringify(sample));

describe("replay app wiring (fake clock)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
    document.body.innerHTML = '<div id="app"></div>';
  });
  afterEach(() => vi.useRealTimers());

  test("each alert reaches the panel once per loop, and each link change once", async () => {
    const alerts = vi.fn();
    const links = vi.fn();
    const offA = hubEvents.onAlert(alerts);
    const offL = hubEvents.onLink((l) => links(l.state));
    location.hash = "#/status";
    await mountReplayApp(document.getElementById("app")!, {
      base: "./", fetchImpl: async (u) => (u.endsWith("replay.json") ? replayJson() : new Response("", { status: 404 })),
    });
    await vi.advanceTimersByTimeAsync(8500);
    expect(alerts).not.toHaveBeenCalled();
    expect(links.mock.calls.map((c) => c[0])).toEqual(["contact", "blackout"]);
    await vi.advanceTimersByTimeAsync(500); // position 9000
    expect(alerts).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2500); // up to the end of the loop: no repeat
    expect(alerts).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(500); // loop: position 0
    expect(links.mock.calls.map((c) => c[0])).toEqual(["contact", "blackout", "contact"]);
    await vi.advanceTimersByTimeAsync(9000); // position 9000 of the second loop
    expect(alerts).toHaveBeenCalledTimes(2);
    expect(links.mock.calls.map((c) => c[0])).toEqual(["contact", "blackout", "contact", "blackout"]);
    offA();
    offL();
  });

  test("a stalled exercise file does not hold the replay back", async () => {
    location.hash = "";
    const root = document.getElementById("app")!;
    const mounted = mountReplayApp(root, {
      base: "./", fetchImpl: (u) => (u.endsWith("replay.json") ? Promise.resolve(replayJson()) : new Promise<Response>(() => {})),
    });
    await vi.advanceTimersByTimeAsync(3000);
    await mounted;
    await vi.advanceTimersByTimeAsync(10);
    expect(root.textContent).toContain("Replay of a recorded session");
    expect(root.querySelector(".p-lift")!.textContent).toContain("No set yet.");
  });
});
