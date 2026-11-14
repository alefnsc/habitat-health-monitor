import { describe, expect, it } from "vitest";
import indexHtml from "../index.html?raw";
import libraryBundle from "../node_modules/@mediapipe/tasks-vision/vision_bundle.mjs?raw";

/*
 * The page serves the pose model and the WASM runtime from its own origin, so it names no third-party host. The pose
 * library still tries to post usage metrics to Google every 60 s (a host that is hard-coded in the library, in
 * node_modules); the page blocks that with a Content-Security-Policy that sets connect-src to 'self'. This test pins
 * the policy and the absence of hosts in the demo's own source.
 */
const POLICY = "connect-src 'self'";

const sources = import.meta.glob<string>(["../../vendor/ground-truth/demo/src/**/*.ts", "../src/**/*.ts"], { query: "?raw", import: "default", eager: true });

const hostsIn = (text: string): string[] => [...text.matchAll(/https?:\/\/([a-zA-Z0-9.-]+)/g)].map((m) => m[1] as string);

describe("network policy", () => {
  it("index.html carries a CSP meta that sets connect-src to exactly 'self', and nothing else", () => {
    const meta = indexHtml.match(/<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"\s*\/?>/);
    expect(meta).not.toBeNull();
    expect(meta?.[1]).toBe(POLICY);
    expect(meta?.[1]).not.toContain(";");
  });

  it("no http or https host appears anywhere in the demo's source, comments included", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(3);
    const found = Object.values(sources)
      .flatMap(hostsIn)
      // the SVG namespace is an identifier, not a request
      .filter((host) => host !== "www.w3.org");
    expect(found).toEqual([]);
  });

  it("the library's only https endpoint is its metrics endpoint, which the policy blocks", () => {
    // If this fails the library changed its endpoints: re-read its privacy notice and re-verify in a browser.
    expect([...new Set(hostsIn(libraryBundle))]).toEqual(["odml.pa.googleapis.com"]);
    expect(POLICY).not.toContain("googleapis");
  });

  it("the model and WASM are same-origin paths", async () => {
    const { POSE_MODEL_URL, POSE_WASM_BASE } = await import("../../vendor/ground-truth/demo/src/pose/source");
    expect(POSE_MODEL_URL).toMatch(/^\/.*models\/pose_landmarker_lite\.task$/);
    expect(POSE_WASM_BASE).toMatch(/^\/.*mediapipe\/wasm$/);
  });
});
