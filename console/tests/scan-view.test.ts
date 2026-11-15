// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { COPY } from "../src/copy";
import { packScanner } from "../src/views/scan";

const cat = { items: [{ id: "bar" }] };
const q = <T extends Element>(root: Element, sel: string) => root.querySelector(sel) as T;
const button = (root: Element, text: string) =>
  [...root.querySelectorAll("button")].find((b) => b.textContent === text) as HTMLButtonElement;

describe("pack scanner panel (D44)", () => {
  beforeEach(() => {
    HTMLMediaElement.prototype.play = async () => {};
  });
  afterEach(() => vi.useRealTimers());

  test("a typed pack code picks the food", () => {
    const picked: string[] = [];
    const s = packScanner(() => cat, (id) => picked.push(id), { detector: () => null, getStream: async () => { throw new Error("no"); } });
    q<HTMLInputElement>(s.node, "#food-code").value = "hhm-food:bar";
    button(s.node, COPY["food.useCode"]).click();
    expect(picked).toEqual(["bar"]);
  });

  test("an unknown typed code picks nothing and says so", () => {
    const picked: string[] = [];
    const s = packScanner(() => cat, (id) => picked.push(id), { detector: () => null, getStream: async () => { throw new Error("no"); } });
    q<HTMLInputElement>(s.node, "#food-code").value = "hhm-food:nope";
    button(s.node, COPY["food.useCode"]).click();
    expect(picked).toEqual([]);
    expect(s.node.textContent).toContain(COPY["food.scanUnknown"]);
  });

  test("without a built-in detector the panel asks for the typed code", async () => {
    const s = packScanner(() => cat, () => {}, { detector: () => null, getStream: async () => { throw new Error("no"); } });
    button(s.node, COPY["food.scanPack"]).click();
    await Promise.resolve();
    expect(s.node.textContent).toContain(COPY["food.scanUnavailable"]);
  });

  test("a scanned pack picks the food and closes the camera", async () => {
    vi.useFakeTimers();
    const picked: string[] = [];
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    const detector = { detect: async () => [{ rawValue: "https://example.org" }, { rawValue: "hhm-food:bar" }] };
    const s = packScanner(() => cat, (id) => picked.push(id), { detector: () => detector, getStream: async () => stream });
    button(s.node, COPY["food.scanPack"]).click();
    await vi.advanceTimersByTimeAsync(600);
    expect(picked).toEqual(["bar"]);
    expect(stop).toHaveBeenCalled();
    expect(q<HTMLVideoElement>(s.node, "video").hidden).toBe(true);
  });

  test("closing the screen while the camera opens stops the camera", async () => {
    vi.useFakeTimers();
    const stop = vi.fn();
    let open!: (s: MediaStream) => void;
    const detect = vi.fn(async () => []);
    const s = packScanner(() => cat, () => {}, {
      detector: () => ({ detect }),
      getStream: () => new Promise<MediaStream>((r) => (open = r)),
    });
    button(s.node, COPY["food.scanPack"]).click();
    s.stop();
    open({ getTracks: () => [{ stop }] } as unknown as MediaStream);
    await vi.advanceTimersByTimeAsync(600);
    expect(stop).toHaveBeenCalled();
    expect(detect).not.toHaveBeenCalled();
  });

  test("a second click while the camera opens does not open a second camera", async () => {
    const getStream = vi.fn(() => new Promise<MediaStream>(() => {}));
    const s = packScanner(() => cat, () => {}, { detector: () => ({ detect: async () => [] }), getStream });
    button(s.node, COPY["food.scanPack"]).click();
    await Promise.resolve();
    button(s.node, COPY["food.scanPack"]).click();
    await Promise.resolve();
    expect(getStream).toHaveBeenCalledTimes(1);
  });

  test("a code typed before the food list loads is not called unknown", () => {
    const s = packScanner(() => null, () => {}, { detector: () => null, getStream: async () => { throw new Error("no"); } });
    q<HTMLInputElement>(s.node, "#food-code").value = "hhm-food:bar";
    button(s.node, COPY["food.useCode"]).click();
    expect(s.node.textContent).toContain(COPY["food.scanCatalogLoading"]);
    expect(s.node.textContent).not.toContain(COPY["food.scanUnknown"]);
  });
});
