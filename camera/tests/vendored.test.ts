import { describe, expect, test } from "vitest";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { analyzeSession } from "@ground-truth/capture";

const V = join(__dirname, "..", "..", "vendor", "ground-truth");
const pinned = readFileSync(join(V, "PINNED"), "utf8");
const line = (k: string) => pinned.split("\n").find((l) => l.startsWith(`${k}=`))?.slice(k.length + 1) ?? "";

describe("vendored ground-truth", () => {
  test("test_pinned_file", () => {
    expect(line("url")).toBe("https://github.com/alefnsc/ground-truth");
    expect(line("commit")).toMatch(/^[0-9a-f]{40}$/);
    expect(line("vendored_at") >= "2026-11-14").toBe(true);
    const paths = line("paths");
    for (const p of ["packages/physics", "packages/capture", "packages/demo/src/pose/source.ts", "packages/demo/scripts/verify-model.mjs"]) {
      expect(paths).toContain(p);
    }
  });

  test("test_licence_present", () => {
    const lic = readFileSync(join(V, "LICENSE"), "utf8");
    expect(lic).toContain("Apache License");
    expect(lic).toContain("Version 2.0");
    expect(readFileSync(join(V, "NOTICE"), "utf8")).toContain(line("commit"));
  });

  test("test_alias_resolves_to_vendor", () => {
    expect(typeof analyzeSession).toBe("function");
  });

  test("test_demo_modules_present", () => {
    for (const f of ["src/pose/source.ts", "src/pose/landmarks.ts", "src/model/captureFlow.ts", "src/model/scenarios.ts", "scripts/copy-wasm.mjs", "scripts/verify-model.mjs"]) {
      const p = join(V, "demo", f);
      expect(existsSync(p), f).toBe(true);
      expect(statSync(p).size).toBeGreaterThan(0);
    }
  });

  test("test_no_registry_copy", () => {
    expect(existsSync(join(__dirname, "..", "node_modules", "@ground-truth"))).toBe(false);
  });
});
