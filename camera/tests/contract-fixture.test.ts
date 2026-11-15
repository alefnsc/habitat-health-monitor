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
  test("the camera still sends exactly the messages in data/contract/camera-reps.v1.jsonl", () => {
    const lines = cameraMessages();
    if (process.env.WRITE_CONTRACT_FIXTURE) writeFileSync(FIXTURE, `${lines.join("\n")}\n`);
    expect(lines).toEqual(readFileSync(FIXTURE, "utf8").trimEnd().split("\n"));
  });

  test("the fixture covers every exercise and a simulated gravity", () => {
    const msgs = readFileSync(FIXTURE, "utf8").trimEnd().split("\n").map((l) => JSON.parse(l));
    expect(new Set(msgs.map((m) => m.exercise))).toEqual(new Set(EXERCISE_MENU.map((e) => e.id)));
    expect(msgs.some((m) => m.g !== 9.81)).toBe(true);
  });
});
