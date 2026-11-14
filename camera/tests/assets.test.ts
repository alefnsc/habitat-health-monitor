import { describe, expect, test } from "vitest";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import config from "../vite.config";

const root = join(__dirname, "..");
const pinned = readFileSync(join(root, "..", "vendor", "ground-truth", "PINNED"), "utf8");
const sha = pinned.match(/commit=([0-9a-f]{40})/)![1];

describe("assets", () => {
  test("test_model_checksum", () => {
    const f = join(root, "public", "models", "pose_landmarker_lite.task");
    expect(statSync(f).size).toBe(5777746);
    expect(createHash("sha256").update(readFileSync(f)).digest("hex")).toBe(
      "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
    );
  });

  test("test_wasm_copied", () => {
    const d = join(root, "public", "mediapipe", "wasm");
    if (!existsSync(d)) throw new Error("run npm --prefix camera run predev first");
    expect(readdirSync(d).some((n) => n.endsWith(".wasm"))).toBe(true);
  });

  test("test_vite_base", () => {
    expect((config as { base: string }).base).toBe("/camera/");
  });

  test("test_licence_files", () => {
    expect(readFileSync(join(root, "public", "LICENSE.txt"), "utf8")).toContain("Apache License");
    expect(readFileSync(join(root, "public", "NOTICE.txt"), "utf8")).toContain(sha);
  });

  test("test_csp_same_origin", () => {
    expect(readFileSync(join(root, "index.html"), "utf8")).toMatch(/Content-Security-Policy[^>]*connect-src 'self'/);
  });
});
