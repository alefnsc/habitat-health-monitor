import { describe, expect, test } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const DIST = join(__dirname, "..", "dist");

// Fixed allowlist: found by scanning the built dist. None is requested at run time: the page's CSP is
// connect-src 'self', and the model and WASM load from this origin. Each host names where it was found.
const ALLOWED_HOSTS = [
  "github.com", // LICENSE.txt/NOTICE.txt (ground-truth URL) and the bundled library's comments
  "developer.mozilla.org", // assets/index-*.js: @mediapipe/tasks-vision comments and error text
  "www.khronos.org", // assets/index-*.js: WebGL spec references in the library
  "www.ietf.org", // mediapipe/wasm/*.js: Emscripten comments
  "tools.ietf.org", // mediapipe/wasm/*.js: Emscripten comments
  "webkit.org", // assets/index-*.js: bug references in the library
  "bugzil.la", // assets/index-*.js: bug references in the library
  "unicode.org", // mediapipe/wasm/*.js: Emscripten comments
  "server.com", // mediapipe/wasm/*.js: Emscripten example URL in a comment
  "pubs.opengroup.org", // mediapipe/wasm/*.js: Emscripten comments
  "kripken.github.io", // mediapipe/wasm/*.js: Emscripten comments
  "en.wikipedia.org", // mediapipe/wasm/*.js: Emscripten comments
  "storage.googleapis.com", // models/NOTICE.md: the model's source URL (documentation only)
  "www.apache.org", // LICENSE.txt: licence header
  "odml.pa.googleapis.com", // assets/index-*.js: the library's metrics endpoint, blocked by the page's CSP
  "localhost", // assets/index-*.js: the insecure-context sentence names http://localhost:8000/camera/
];

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? files(join(dir, e.name)) : [join(dir, e.name)]));
}

describe("offline bundle (camera)", () => {
  test("test_no_external_hosts_camera", () => {
    if (!existsSync(DIST)) throw new Error("run npm --prefix camera run build first");
    const found = new Set<string>();
    for (const f of files(DIST)) {
      // Binary files (the model and the WASM runtime) hold byte strings, not page URLs; their loading is pinned by the CSP.
      if (f.endsWith(".task") || f.endsWith(".wasm")) continue;
      for (const m of readFileSync(f, "utf8").matchAll(/https?:\/\/([A-Za-z0-9.-]+)/g)) found.add(m[1]);
    }
    expect([...found].filter((h) => !ALLOWED_HOSTS.includes(h))).toEqual([]);
  });

  test("test_assets_present", () => {
    if (!existsSync(DIST)) throw new Error("run npm --prefix camera run build first");
    expect(statSync(join(DIST, "models", "pose_landmarker_lite.task")).size).toBe(5777746);
    expect(readdirSync(join(DIST, "mediapipe", "wasm")).some((n) => n.endsWith(".wasm"))).toBe(true);
    expect(existsSync(join(DIST, "LICENSE.txt"))).toBe(true);
    expect(existsSync(join(DIST, "NOTICE.txt"))).toBe(true);
  });

  test("the built page keeps the same-origin CSP", () => {
    expect(readFileSync(join(DIST, "index.html"), "utf8")).toContain("connect-src 'self'");
  });
});
