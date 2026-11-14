// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { Spot } from "./habitat";
import type { LinkFrame } from "./linkview";
import { renderOverview } from "./overview";

const FRAME: LinkFrame = {
  lightTimeMin: 12, holdS: 12, timeScale: 60,
  packets: [{ x: 0.2, big: false }, { x: 0.7, big: true }],
  gap: null, marsDown: false, earthDark: false, cause: null,
};

function draw(frame: Partial<LinkFrame> = {}, lit: Spot[] = [], present: Spot[] | null = null): HTMLElement {
  const root = document.createElement("div");
  renderOverview(root, { ...FRAME, ...frame }, new Set(lit), present && new Set(present));
  return root;
}

describe("renderOverview: link", () => {
  it("shows the one-way light-time in minutes and the demo hold", () => {
    const text = draw().textContent!;
    expect(text).toContain("12 min one-way");
    expect(text).toContain("×60");
    expect(text).toContain("12 s");
  });

  it("draws one dot per packet in flight, big ones marked", () => {
    const root = draw();
    expect(root.querySelectorAll("circle.packet").length).toBe(2);
    expect(root.querySelectorAll("circle.packet.big").length).toBe(1);
  });

  it("shows the blackout badge and gap only while blackout signal is on the line", () => {
    expect(draw().querySelector(".blackout")).toBeNull();
    const root = draw({ gap: [0, 0.5], marsDown: true, cause: "scheduled" });
    expect(root.querySelector(".blackout")!.textContent).toContain("BLACKOUT");
    expect(root.querySelector(".blackout")!.textContent).toContain("scheduled");
    expect(root.querySelector("line.gap")).not.toBeNull();
  });

  it("labels each end of the link with its state", () => {
    expect(draw().textContent).toContain("sending");
    expect(draw().textContent).toContain("receiving");
    const dark = draw({ gap: [0, 1], marsDown: true, earthDark: true, cause: "scheduled" }).textContent!;
    expect(dark).toContain("link down, queueing");
    expect(dark).toContain("no signal");
  });

  it("says so when no light-time is reported yet", () => {
    expect(draw({ lightTimeMin: null, holdS: null, timeScale: null }).textContent)
      .toContain("Light-time not reported yet");
  });
});

describe("renderOverview: habitat map", () => {
  it("draws a box for every node", () => {
    const root = draw();
    for (const s of ["cabin", "camera", "tilt", "hub", "ring"]) {
      expect(root.querySelector(`[data-spot="${s}"]`)).not.toBeNull();
    }
    const text = root.textContent!;
    for (const label of ["UNO", "DHT11", "buzzer", "Camera", "NodeMCU", "KY-017", "Raspberry Pi", "Ring import"]) {
      expect(text).toContain(label);
    }
  });

  it("lights exactly the boxes whose data just reached Earth", () => {
    const root = draw({}, ["cabin", "hub"]);
    expect([...root.querySelectorAll(".node.lit")].map((e) => e.getAttribute("data-spot")).sort())
      .toEqual(["cabin", "hub"]);
  });

  it("marks boxes with no data in this replay", () => {
    const root = draw({}, [], ["cabin", "hub", "ring"]);
    expect(root.querySelector('[data-spot="camera"]')!.classList.contains("absent")).toBe(true);
    expect(root.querySelector('[data-spot="camera"]')!.textContent).toContain("no data in this replay");
    expect(root.querySelector('[data-spot="cabin"]')!.classList.contains("absent")).toBe(false);
    expect(draw().textContent).not.toContain("no data in this replay");
  });
});
