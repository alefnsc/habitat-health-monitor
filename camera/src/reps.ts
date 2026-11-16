import type { RefusalReason, RepResult } from "@ground-truth/capture";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyseRecording, captureInputProblem, refusalSentences, type CaptureInputs, type CaptureOutcome } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { COPY } from "./copy";
import type { Sequencer } from "./seq";

export { analyseRecording };

// Picked by the astronaut before the set: wrist-tracked vertical lifts only (no squat, the body mass moves).
export type Exercise = "curl" | "overhead_press" | "row";

export const EXERCISE_MENU: { id: Exercise; label: string }[] = (["curl", "overhead_press", "row"] as const).map((id) => ({
  id,
  label: COPY[`exercise.${id}`],
}));

export const parseExercise = (value: string): Exercise | null => EXERCISE_MENU.find((e) => e.id === value)?.id ?? null;

export const exerciseCaption = (id: Exercise): string =>
  COPY["result.exercise"].replace("{label}", EXERCISE_MENU.find((e) => e.id === id)?.label ?? id);

export interface RepMessage {
  v: 1;
  node: "camera";
  boot: number;
  seq: number;
  age_ms: number;
  type: "rep";
  session: string;
  rep: number;
  src: "camera";
  peak_n: number;
  work_j: number;
  rom_m: number | null;
  g: number;
  mass_kg: number;
  t0_ms: number;
  t1_ms: number;
  work_ecc_j: number;
  t_con_ms: number;
  t_ecc_ms: number;
  t_turn_ms: number;
  exercise: Exercise;
}

export interface RepContext {
  session: string;
  exercise: Exercise;
  g: number;
  mass_kg: number;
  boot: number;
  seq: Sequencer;
  firstFramePerfMs: number;
  nowPerfMs: number;
}

// No messages after a refusal. age_ms is anchored on the first recorded frame, not on any HTTP response.
export function toRepMessages(result: { ok: true; reps: RepResult[] } | { ok: false }, ctx: RepContext): RepMessage[] {
  if (!result.ok) return [];
  return result.reps.map((r, i) => {
    const t0 = Math.round(r.startS * 1000);
    const t1 = Math.round((r.startS + r.durationS) * 1000);
    // Turnaround: the vendored lift ends at the first sample at the top level (D39).
    const turn = Math.min(t1, Math.max(t0, Math.round((r.startS + r.liftDurationS) * 1000)));
    return {
      v: 1,
      node: "camera",
      boot: ctx.boot,
      seq: ctx.seq.next(),
      age_ms: Math.max(0, Math.round(ctx.nowPerfMs - (ctx.firstFramePerfMs + t1))),
      type: "rep",
      session: ctx.session,
      rep: i + 1,
      src: "camera",
      peak_n: r.peakForceN,
      work_j: r.positiveWorkJ,
      rom_m: r.rangeOfMotionM,
      g: ctx.g,
      mass_kg: ctx.mass_kg,
      t0_ms: t0,
      t1_ms: t1,
      work_ecc_j: Math.max(0, -r.negativeWorkJ),
      t_con_ms: turn - t0,
      t_ecc_ms: t1 - turn,
      t_turn_ms: turn,
      exercise: ctx.exercise,
    };
  });
}

export const refusalText = (reasons: RefusalReason[]): string[] => refusalSentences(reasons);

export const inputProblemText = (inputs: CaptureInputs): string | null => captureInputProblem(inputs);

// NASA NSSDC Mars Fact Sheet, surface gravity (mean): 3.73 m/s² (equatorial 3.69). The vendored table's Mars value
// is not on that page; the console's four-places card uses 3.73 too.
export const MARS_G_MS2 = 3.73;

export const ENVIRONMENT_MENU = (["EARTH", "MOON", "MARS", "ISS"] as const).map((id) => ({
  id,
  label: COPY[`env.${id}`],
  g: id === "MARS" ? MARS_G_MS2 : G_ENV_MS2[id],
}));

// The line under the result table: work uses the configured g, taken from the selected menu entry.
export const gNoteText = (g: number): string =>
  COPY["result.gNote"]
    .replace("{g}", g.toFixed(2))
    .replace("{env}", ENVIRONMENT_MENU.find((e) => e.g === g)?.label ?? "custom");

export interface ResultRow {
  rep: number;
  peakN: number;
  workJ: number;
  eccJ: number;
  tConS: number;
  tEccS: number;
  romM: number;
  badge: string;
  notes: string[];
}

export function resultView(outcome: CaptureOutcome): { rows: ResultRow[]; grade: string | null; notes: string[] } {
  if (outcome.kind === "refused") {
    return { rows: [], grade: null, notes: outcome.reasons.map((r) => r.sentence) };
  }
  return {
    rows: outcome.reps.map((r) => ({
      rep: r.index,
      peakN: r.rep.peakForceN,
      workJ: r.rep.positiveWorkJ,
      eccJ: Math.max(0, -r.rep.negativeWorkJ),
      tConS: r.rep.liftDurationS,
      tEccS: Math.max(0, r.rep.durationS - r.rep.liftDurationS),
      romM: r.rep.rangeOfMotionM,
      badge: COPY["result.estimate"],
      notes: r.notes,
    })),
    grade: outcome.confidence,
    notes: [COPY["camera.estimate"], COPY["result.filter"], COPY["result.gradeNote"]],
  };
}
