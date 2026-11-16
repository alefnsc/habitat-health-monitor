// @vitest-environment jsdom
// DOM wiring of the set controls (setview.ts): mounted in jsdom with a fake camera page and a mocked hub client.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { PageState } from "../src/main";
import { COPY } from "../src/copy";
import { ENVIRONMENT_MENU } from "../src/reps";

const api = vi.hoisted(() => ({
  startSession: vi.fn(),
  endSession: vi.fn(),
  postRep: vi.fn(),
  postRepsWithRetry: vi.fn(),
}));
vi.mock("../src/session", async (orig) => ({ ...(await orig<typeof import("../src/session")>()), ...api }));

import { mountSet } from "../src/setview";

function fakePage(opts: { frameCallback?: boolean } = {}) {
  let onScale: ((m: number) => void) | null = null;
  const tracker = { stop: vi.fn() };
  const video = document.createElement("video");
  if (opts.frameCallback !== false) Object.assign(video, { requestVideoFrameCallback: () => 0 });
  const page = {
    video,
    record: vi.fn(() => tracker),
    resumePreview: vi.fn(),
    setSetHost: vi.fn(),
    onScale: (cb: (m: number) => void) => { onScale = cb; },
    getSource: () => null,
    getScale: () => null,
    getLandmarker: () => null,
  };
  return { page: page as unknown as PageState, raw: page, tracker, calibrate: (m = 0.002) => onScale!(m) };
}

function mount(opts?: { frameCallback?: boolean }) {
  const host = document.createElement("div");
  document.body.append(host);
  const p = fakePage(opts);
  mountSet(host, p.page);
  const q = <T extends Element>(s: string) => host.querySelector(s) as T;
  const button = (t: string) => [...host.querySelectorAll("button")].find((b) => b.textContent === t)!;
  const pick = (id: string, value: string) => {
    const s = q<HTMLSelectElement>(`#${id}`);
    s.value = value;
    s.dispatchEvent(new Event("change"));
  };
  return {
    ...p, host, pick, start: button("Start set"), stop: button("Stop set"),
    msg: () => q<HTMLElement>('p[role="status"]').textContent,
    disabled: (id: string) => q<HTMLElement>(`#${id}`).hasAttribute("disabled"),
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  api.startSession.mockResolvedValue({ session: "s-1", mass_kg: 10, g: 9.81, crew: "crew-a", exercise: "row" });
  api.endSession.mockResolvedValue({});
});
afterEach(() => {
  vi.clearAllMocks();
  document.body.replaceChildren();
});

describe("set controls", () => {
  test("crew and exercise start on a disabled placeholder: no default pick", () => {
    const m = mount();
    for (const id of ["crew", "exercise"]) {
      const s = m.host.querySelector(`#${id}`) as HTMLSelectElement;
      expect(s.value).toBe("");
      expect(s.options[0].disabled).toBe(true);
    }
    expect(m.start.hasAttribute("disabled")).toBe(false);
    expect(m.stop.hasAttribute("disabled")).toBe(true);
  });

  test("Start refuses without a crew, then without an exercise, then before calibration", async () => {
    const m = mount();
    m.start.click();
    await flush();
    expect(m.msg()).toBe(COPY["crew.needed"]);
    m.pick("crew", "crew-a");
    m.start.click();
    await flush();
    expect(m.msg()).toBe(COPY["exercise.needed"]);
    m.pick("exercise", "row");
    m.start.click();
    await flush();
    expect(m.msg()).toBe("Calibrate the scale first.");
    expect(api.startSession).not.toHaveBeenCalled();
    expect(m.raw.record).not.toHaveBeenCalled();
  });

  test("a calibrated Start opens a session with the picked values and locks the pickers", async () => {
    const m = mount();
    m.calibrate();
    m.pick("crew", "crew-b");
    m.pick("exercise", "row");
    m.pick("env", String(ENVIRONMENT_MENU.find((e) => e.id === "MOON")!.g));
    m.start.click();
    await flush();
    expect(api.startSession).toHaveBeenCalledWith({ mass_kg: 10, g: 1.62, crew: "crew-b", exercise: "row" });
    expect(m.raw.record).toHaveBeenCalledTimes(1);
    expect(m.host.querySelector("#session-id")!.textContent).toBe("s-1");
    expect(m.start.hasAttribute("disabled")).toBe(true);
    expect(m.disabled("crew") && m.disabled("exercise")).toBe(true);
    expect(m.stop.hasAttribute("disabled")).toBe(false);
  });

  test("a hub error on Start is shown and nothing records", async () => {
    api.startSession.mockRejectedValueOnce(new Error("hub unreachable"));
    const m = mount();
    m.calibrate();
    m.pick("crew", "crew-a");
    m.pick("exercise", "curl");
    m.start.click();
    await flush();
    expect(m.msg()).toBe("hub unreachable");
    expect(m.raw.record).not.toHaveBeenCalled();
    expect(m.start.hasAttribute("disabled")).toBe(false);
  });

  test("Stop ends the session, unlocks the pickers and resumes the preview; an empty set sends nothing", async () => {
    const m = mount();
    m.calibrate();
    m.pick("crew", "crew-a");
    m.pick("exercise", "curl");
    m.start.click();
    await flush();
    m.stop.click();
    await flush();
    expect(m.tracker.stop).toHaveBeenCalledTimes(1);
    expect(api.endSession).toHaveBeenCalledWith("s-1");
    expect(m.start.hasAttribute("disabled")).toBe(false);
    expect(m.disabled("crew") || m.disabled("exercise")).toBe(false);
    expect(m.stop.hasAttribute("disabled")).toBe(true);
    expect(api.postRepsWithRetry).not.toHaveBeenCalled();
    expect(m.raw.resumePreview).toHaveBeenCalledTimes(1);
  });

  test("a browser without per-frame timing cannot start, and says why", () => {
    const m = mount({ frameCallback: false });
    expect(m.start.hasAttribute("disabled")).toBe(true);
    expect(m.msg()).not.toBe("");
  });
});
