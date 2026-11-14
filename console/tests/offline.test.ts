import { describe, expect, test } from "vitest";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const DIST = join(__dirname, "..", "dist");

// Fixed allowlist. The console makes no cross-origin request: these hosts appear only as link targets (anchor hrefs)
// in the bundled data files, and the browser fetches none of them unless the user clicks.
const ALLOWED_HOSTS = [
  "humanresearchroadmap.nasa.gov", // data/guidance.json and data/nasa/hrp_risks.json risk page links
  "standards.nasa.gov", // data/thresholds.json source URLs (NASA-STD-3001 PDFs)
  "www.rcp.ac.uk", // data/thresholds.json clinical source URL
  "www.nasa.gov", // data/guidance.json / thresholds.json source URLs
  "www.ahajournals.org", // data/thresholds.json clinical source URL
  "www.aasm.org", // data/thresholds.json clinical source URL
  "github.com", // data links in the bundled data and uPlot's licence header
  "doi.org", // data/thresholds.json clinical source URL
];

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? files(join(dir, e.name)) : [join(dir, e.name)]));
}

describe("offline bundle (console)", () => {
  test("test_no_external_hosts_console", () => {
    if (!existsSync(DIST)) throw new Error("run npm --prefix console run build first");
    const found = new Set<string>();
    for (const f of files(DIST)) {
      for (const m of readFileSync(f, "utf8").matchAll(/https?:\/\/([A-Za-z0-9.-]+)/g)) found.add(m[1]);
    }
    expect([...found].filter((h) => !ALLOWED_HOSTS.includes(h))).toEqual([]);
  });

  test("no web fonts and no external script or stylesheet tags", () => {
    if (!existsSync(DIST)) throw new Error("run npm --prefix console run build first");
    expect(files(DIST).filter((f) => /\.(woff2?|ttf|otf)$/.test(f))).toEqual([]);
    const html = readFileSync(join(DIST, "index.html"), "utf8");
    expect(/<(script|link)[^>]+(src|href)="https?:/.test(html)).toBe(false);
  });
});
