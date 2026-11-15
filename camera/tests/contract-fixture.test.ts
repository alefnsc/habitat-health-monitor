import { describe, expect, test } from "vitest";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createSequencer } from "../src/seq";
import { ENVIRONMENT_MENU, EXERCISE_MENU, analyseRecording, toRepMessages } from "../src/reps";
import { syntheticSession } from "../../vendor/ground-truth/capture/test/helpers";

// The camera half of a shared contract fixture: the exact messages the camera page POSTs to /api/reps for a few
// seeded synthetic sets. hub/tests/test_contract_camera_fixture.py parses every line with the hub's parse_rep, so a
// change on either side that breaks the other fails a test. After a deliberate change to the rep message, rewrite
// the file with: WRITE_CONTRACT_FIXTURE=1 npx vitest run tests/contract-fixture.test.ts
const FIXTURE = join(__dirname, "..", "..", "data", "contract", "camera-reps.v1.jsonl");

// The pose maths' floats differ in their last digits between CPUs and V8 builds: the fixture was written on an
// arm64 Mac, and Linux x64 CI gives e.g. peak_n 126.81911391102282 for 126.81911391102321 (about 3e-15 relative).
// So keys, their order, integers and strings must match exactly; other numbers within a relative 1e-9, far below
// any real change to the maths.
const REL_TOL = 1e-9;

/** Why `got` is not the fixture message `want`, or null when it is. */
function messageDiff(got: Record<string, unknown>, want: Record<string, unknown>): string | null {
  const gk = Object.keys(got).join(","), wk = Object.keys(want).join(",");
  if (gk !== wk) return `keys: ${gk} vs ${wk}`;
  for (const k of Object.keys(want)) {
    const a = got[k], b = want[k];
    if (typeof a === "number" && typeof b === "number" && !(Number.isInteger(a) && Number.isInteger(b))) {
      if (!(Math.abs(a - b) <= REL_TOL * Math.max(1, Math.abs(b)))) return `${k}: ${a} vs ${b}`;
    } else if (a !== b) {
      return `${k}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`;
    }
  }
  return null;
}

const SETS = [
  ...EXERCISE_MENU.map((e) => ({ exercise: e.id, env: "EARTH" as const })),
  { exercise: "curl" as const, env: "MOON" as const }, // a simulated gravity, kept out of Earth-g training work
];

function cameraMessages(): string[] {
  const seq = createSequencer(1794657600);
  return SETS.flatMap((s, i) => {
    const g = ENVIRONMENT_MENU.find((e) => e.id === s.env)!.g;
    const frames = syntheticSession({ reps: 2, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 30, noiseM: 0, seed: i + 1, metersPerUnit: 1 });
    const outcome = analyseRecording(frames, { massKg: 10, gEnvMs2: g, deviceForceN: 0, metersPerUnit: 1 }, { id: "fixture", title: "fixture" });
    if (outcome.kind !== "analysed") throw new Error(`${s.exercise} at ${s.env}: ${outcome.kind}`);
    // As setview.ts does after a set.
    const msgs = toRepMessages({ ok: true, reps: outcome.reps.map((r) => r.rep) }, {
      session: `fixture-${i + 1}`, exercise: s.exercise, g, mass_kg: 10, boot: 1794657600, seq, firstFramePerfMs: 1000, nowPerfMs: 30000,
    });
    expect(msgs.length, `${s.exercise} at ${s.env}`).toBeGreaterThan(0);
    return msgs.map((m) => JSON.stringify(m));
  });
}

describe("camera → hub contract fixture", () => {
  test("the camera still sends the messages in data/contract/camera-reps.v1.jsonl", () => {
    const lines = cameraMessages();
    if (process.env.WRITE_CONTRACT_FIXTURE) writeFileSync(FIXTURE, `${lines.join("\n")}\n`);
    const want = readFileSync(FIXTURE, "utf8").trimEnd().split("\n");
    expect(lines.length).toBe(want.length);
    lines.forEach((l, i) => expect(messageDiff(JSON.parse(l), JSON.parse(want[i])), `line ${i + 1}`).toBeNull());
  });

  test("the comparison ignores last-digit float noise and nothing else", () => {
    const want = JSON.parse(readFileSync(FIXTURE, "utf8").split("\n")[0]);
    // The values Linux x64 CI produced for line 1 (run 43746164229).
    expect(messageDiff({ ...want, peak_n: 126.81911391102282 }, want)).toBeNull();
    expect(messageDiff({ ...want, work_j: want.work_j * (1 + 1e-6) }, want)).toMatch(/^work_j:/);
    expect(messageDiff({ ...want, t1_ms: want.t1_ms + 1 }, want)).toMatch(/^t1_ms:/);
    expect(messageDiff({ ...want, exercise: "row" }, want)).toMatch(/^exercise:/);
    expect(messageDiff({ ...want, rom_m: null }, want)).toMatch(/^rom_m:/);
    const { work_ecc_j: _dropped, ...fewer } = want;
    expect(messageDiff(fewer, want)).toMatch(/^keys:/);
    expect(messageDiff({ ...want, extra: 1 }, want)).toMatch(/^keys:/);
  });

  test("the fixture covers every exercise and a simulated gravity", () => {
    const msgs = readFileSync(FIXTURE, "utf8").trimEnd().split("\n").map((l) => JSON.parse(l));
    expect(new Set(msgs.map((m) => m.exercise))).toEqual(new Set(EXERCISE_MENU.map((e) => e.id)));
    expect(msgs.some((m) => m.g !== 9.81)).toBe(true);
  });
});
