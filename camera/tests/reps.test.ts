import { describe, expect, test } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import type { RefusalReason, RepResult, SessionResult } from "@ground-truth/capture";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { createSequencer } from "../src/seq";
import { ENVIRONMENT_MENU, EXERCISE_MENU, MARS_G_MS2, analyseRecording, exerciseCaption, inputProblemText, parseExercise, refusalText, resultView, toRepMessages } from "../src/reps";
import { refusalSentences, repNotes } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { syntheticSession } from "../../vendor/ground-truth/capture/test/helpers";
import { ruleBrand, ruleCalories, ruleDiagnosis, ruleNonEnglish, ruleTreatmentDose } from "../../console/tests/honesty";

const rep = (o: Partial<RepResult>): RepResult => ({
  startS: 0, durationS: 2, liftDurationS: 1, filterLimited: false, rangeOfMotionM: 0.5, pathLengthM: 1,
  trimmedRangeFraction: 1, positiveWorkJ: 10, negativeWorkJ: -5, peakForceN: 100, impulseNs: 1, ...o,
});
const ok = (reps: RepResult[]): SessionResult =>
  ({ ok: true, reps, totalPositiveWorkJ: 0, maxPeakForceN: 0, quality: {}, provenance: { confidence: "MEDIUM" } }) as unknown as SessionResult;
const ctx = (seq = createSequencer(1794657600)) => ({
  session: "s-1794657600000", g: 9.81, mass_kg: 10, boot: 1794657600, seq, firstFramePerfMs: 1000, nowPerfMs: 9000,
  exercise: "curl" as const,
});
const ALL: RefusalReason[] = ["NO_SCALE", "LOW_FRAME_RATE", "LANDMARK_LOST", "GAP_TOO_LONG", "TOO_SHORT", "NO_REPS"];

describe("reps", () => {
  test("test_sequencer", () => {
    const s = createSequencer(1794657600);
    expect(s.boot).toBe(1794657600);
    expect([s.next(), s.next(), s.next()]).toEqual([1, 2, 3]);
  });

  test("test_rep_mapping", () => {
    const m = toRepMessages(
      ok([rep({ startS: 1.2, durationS: 2.1, peakForceN: 231.4, positiveWorkJ: 38.6, rangeOfMotionM: 0.52 }), rep({ startS: 4, durationS: 2 })]),
      ctx(),
    );
    expect(m[0]).toMatchObject({
      v: 1, type: "rep", node: "camera", boot: 1794657600, seq: 1, session: "s-1794657600000", rep: 1, src: "camera",
      peak_n: 231.4, work_j: 38.6, rom_m: 0.52, g: 9.81, mass_kg: 10, t0_ms: 1200, t1_ms: 3300, age_ms: 4700,
    });
    expect(m[1]).toMatchObject({ rep: 2, seq: 2, t0_ms: 4000, t1_ms: 6000 });
  });

  test("test_age_from_first_frame", () => {
    // A late "Start set" response changes nothing: age depends only on the first frame's time and now.
    const m = toRepMessages(ok([rep({ startS: 1.2, durationS: 2.1 })]), ctx());
    expect(m[0].age_ms).toBe(4700);
  });

  test("test_refusal_posts_nothing", () => {
    const refused = { ok: false, reasons: ["NO_SCALE", "TOO_SHORT"], quality: {} } as unknown as SessionResult;
    expect(toRepMessages(refused, ctx())).toEqual([]);
    expect(refusalText(["NO_SCALE", "TOO_SHORT"])).toEqual(refusalSentences(["NO_SCALE", "TOO_SHORT"]));
  });

  test("test_refusal_texts", () => {
    for (const r of ALL) {
      const t = refusalText([r]);
      expect(t).toEqual(refusalSentences([r]));
      expect(t[0].length).toBeGreaterThan(10);
    }
  });

  test("test_vendored_text_lint", () => {
    const texts = [...refusalSentences(ALL), ...repNotes(rep({ filterLimited: true, trimmedRangeFraction: 0.4 }))];
    for (const t of texts) {
      for (const rule of [ruleCalories, ruleDiagnosis, ruleTreatmentDose, ruleBrand, ruleNonEnglish]) expect(rule(t), t).toBe(false);
    }
  });

  test("test_gravity_import", () => {
    // Earth, Moon and the ISS come from the vendored table. Mars is the NASA NSSDC mean surface gravity,
    // 3.73 m/s²: the vendored 3.71 is not on that fact sheet (docs/img/image-facts.md).
    expect(ENVIRONMENT_MENU.map((e) => [e.id, e.g])).toEqual([
      ["EARTH", G_ENV_MS2.EARTH], ["MOON", G_ENV_MS2.MOON], ["MARS", MARS_G_MS2], ["ISS", G_ENV_MS2.ISS],
    ]);
    expect(ENVIRONMENT_MENU.map((e) => e.g)).toEqual([9.81, 1.62, 3.73, 0]);
    const dir = join(__dirname, "..", "src");
    for (const f of readdirSync(dir)) expect(/\b3\.71\b|\b1\.62\b/.test(readFileSync(join(dir, f), "utf8")), f).toBe(false);
  });

  test("test_one_mars_gravity_with_the_panel", () => {
    // The console's four-places card rescales a rep by rep.g; the camera must log the same Mars g.
    const places = readFileSync(join(__dirname, "..", "..", "console", "src", "model", "panel", "places.ts"), "utf8");
    const m = /key: "mars", g: ([0-9.]+)/.exec(places);
    expect(m).not.toBeNull();
    expect(ENVIRONMENT_MENU.find((e) => e.id === "MARS")!.g).toBe(Number(m![1]));
  });

  test("test_iss_zero_g", () => {
    const frames = syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 30, noiseM: 0, seed: 1, metersPerUnit: 1 });
    const inputs = { massKg: 10, gEnvMs2: 0, deviceForceN: 0, metersPerUnit: 1 };
    expect(inputProblemText(inputs)).toBeNull();
    expect(() => analyseRecording(frames, inputs, { id: "t", title: "t" })).not.toThrow();
  });

  test("test_input_problem", () => {
    expect(inputProblemText({ massKg: 0, gEnvMs2: 9.81, deviceForceN: 0, metersPerUnit: 1 })).toEqual(expect.any(String));
    expect(inputProblemText({ massKg: 10, gEnvMs2: 9.81, deviceForceN: 0, metersPerUnit: 1 })).toBeNull();
  });

  test("test_confidence_only_on_success", () => {
    const frames = syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 30, noiseM: 0, seed: 1, metersPerUnit: 1 });
    const good = analyseRecording(frames, { massKg: 10, gEnvMs2: 9.81, deviceForceN: 0, metersPerUnit: 1 }, { id: "t", title: "t" });
    expect(good.kind).toBe("analysed");
    const v = resultView(good);
    expect(v.grade).toMatch(/LOW|MEDIUM|HIGH/);
    expect(v.rows.length).toBe(3);
    expect(v.rows.every((r) => r.badge === "Estimate")).toBe(true);
    const bad = analyseRecording(frames, { massKg: 10, gEnvMs2: 9.81, deviceForceN: 0, metersPerUnit: null }, { id: "t", title: "t" });
    const w = resultView(bad);
    expect(w.grade).toBeNull();
    expect(w.rows).toEqual([]);
  });

  test("test_filter_notes", () => {
    const r = rep({ filterLimited: true, trimmedRangeFraction: 0.5 });
    expect(repNotes(r).length).toBe(2);
    const m = toRepMessages(ok([r]), ctx());
    expect(Object.keys(m[0])).not.toContain("filterLimited");
  });

  test("test_exercise_menu", () => {
    // Only wrist-tracked vertical lifts: the body mass does not move, so the vendored physics fits.
    expect(EXERCISE_MENU.map((e) => e.id)).toEqual(["curl", "overhead_press", "row"]);
    expect(EXERCISE_MENU.map((e) => e.label)).toEqual(["Dumbbell curl", "Overhead press", "Row"]);
    for (const e of EXERCISE_MENU) expect(/squat/i.test(`${e.id} ${e.label}`)).toBe(false);
  });

  test("test_parse_exercise", () => {
    expect(parseExercise("row")).toBe("row");
    expect(parseExercise("overhead_press")).toBe("overhead_press");
    for (const v of ["", "squat", "Row", "curl "]) expect(parseExercise(v)).toBeNull();
  });

  test("test_rep_carries_exercise", () => {
    const m = toRepMessages(ok([rep({}), rep({ startS: 4 })]), { ...ctx(), exercise: "row" });
    expect(m.map((x) => x.exercise)).toEqual(["row", "row"]);
  });

  test("test_exercise_caption", () => {
    expect(exerciseCaption("overhead_press")).toBe("Exercise: Overhead press");
    expect(exerciseCaption("curl")).toBe("Exercise: Dumbbell curl");
  });
});
