import type { RefusalReason, SessionResult } from "@ground-truth/capture";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyseRecording, captureInputProblem, refusalSentences, type CaptureInputs, type CaptureOutcome } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { COPY } from "./copy";
import type { Sequencer } from "./seq";

export { analyseRecording };

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
}

export interface RepContext {
  session: string;
  g: number;
  mass_kg: number;
  boot: number;
  seq: Sequencer;
  firstFramePerfMs: number;
  nowPerfMs: number;
}

// No messages after a refusal. age_ms is anchored on the first recorded frame, not on any HTTP response.
export function toRepMessages(result: SessionResult, ctx: RepContext): RepMessage[] {
  if (!result.ok) return [];
  return result.reps.map((r, i) => {
    const t0 = Math.round(r.startS * 1000);
    const t1 = Math.round((r.startS + r.durationS) * 1000);
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
    };
  });
}

export const refusalText = (reasons: RefusalReason[]): string[] => refusalSentences(reasons);

export const inputProblemText = (inputs: CaptureInputs): string | null => captureInputProblem(inputs);

export const ENVIRONMENT_MENU = (["EARTH", "MOON", "MARS", "ISS"] as const).map((id) => ({
  id,
  label: COPY[`env.${id}`],
  g: G_ENV_MS2[id],
}));

export interface ResultRow {
  rep: number;
  peakN: number;
  workJ: number;
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
      romM: r.rep.rangeOfMotionM,
      badge: COPY["result.estimate"],
      notes: r.notes,
    })),
    grade: outcome.confidence,
    notes: [COPY["camera.estimate"], COPY["result.filter"], COPY["result.gradeNote"]],
  };
}
