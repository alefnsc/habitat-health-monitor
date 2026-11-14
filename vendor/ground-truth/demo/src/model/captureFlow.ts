/**
 * The capture view's logic, pure: the state machine, the two scale methods, the checks on the
 * inputs, the analysis of a recording into either a camera SessionResult or a refusal in plain
 * sentences, and the per-rep flags. The view only draws what this returns.
 */

import {
  FILTER_LIMITED_LIFT_S,
  MAX_GAP_S,
  MAX_LOW_VISIBILITY_FRACTION,
  MIN_CALIBRATION_SPAN,
  MIN_DURATION_S,
  MIN_KNOWN_LENGTH_SPAN,
  MIN_PHASE_DISPLACEMENT_M,
  MIN_RATE_HZ,
  analyzeSession,
  metersPerUnitFromKnownLength,
  metersPerUnitFromStature,
  type PoseFrame,
  type QualityReport,
  type RefusalReason,
  type RepResult,
} from "@ground-truth/capture";
import type { Confidence } from "@ground-truth/physics";
import { DEVICE_FORCE_LIMITS_N, cameraPipelineTag, cameraSession, derive, labelled, source, type Detail, type Quantity, type SessionResult } from "./scenarios";

// ---------------------------------------------------------------------------
// State machine: idle -> calibrating -> ready -> recording -> analysed | refused
// ---------------------------------------------------------------------------

export type FlowState = "idle" | "calibrating" | "ready" | "recording" | "analysed" | "refused" | "failed";
export type FlowEvent = "openSource" | "calibrated" | "recalibrate" | "start" | "analysed" | "refused" | "failed" | "reset";

const TRANSITIONS: Readonly<Record<FlowState, Partial<Record<FlowEvent, FlowState>>>> = {
  idle: { openSource: "calibrating" },
  calibrating: { calibrated: "ready" },
  ready: { start: "recording", recalibrate: "calibrating" },
  recording: { analysed: "analysed", refused: "refused", failed: "failed" },
  analysed: { openSource: "calibrating" },
  refused: { openSource: "calibrating" },
  failed: { openSource: "calibrating" },
};

/** The next state. `reset` goes to idle from anywhere; an event that does not apply leaves the state alone. */
export function transition(state: FlowState, event: FlowEvent): FlowState {
  if (event === "reset") return "idle";
  return TRANSITIONS[state][event] ?? state;
}

/**
 * Which open is the current one. Every open takes a token and checks it after every await; an open that was
 * superseded (a second click, leaving the tab) must release whatever it acquired and do nothing else.
 */
export function createGate(): { next(): number; invalidate(): void; isCurrent(token: number): boolean } {
  let latest = 0;
  return {
    next: () => ++latest,
    invalidate: () => {
      latest += 1;
    },
    isCurrent: (token) => token === latest,
  };
}

export const NO_CAPTURE_TIMESTAMPS =
  "This browser cannot give capture timestamps for video frames (it has no requestVideoFrameCallback), so a recording would carry timing errors that look like movement. Use a current Chrome, Edge, Safari or Firefox.";

/** A sentence when recording must be refused for lack of capture timestamps, else null. */
export function timingProblem(hasFrameCallback: boolean): string | null {
  return hasFrameCallback ? null : NO_CAPTURE_TIMESTAMPS;
}

export const RECORDING_FAILED = "The recording could not be analysed because of an error on this page. Nothing was saved. Record again.";

// ---------------------------------------------------------------------------
// Sentences
// ---------------------------------------------------------------------------

export const SCALE_SENTENCE = "Scale is the largest error in this measurement.";
export const CONFIDENCE_SENTENCE = "Confidence grades the recording conditions, not accuracy; capped until validated on real video.";

const percent = (fraction: number): string => `${Math.round(fraction * 100)} %`;

/** The capture package's refusal reasons, one sentence each. */
const SENTENCES: Readonly<Record<RefusalReason, string>> = {
  NO_SCALE: "There is no scale yet: calibrate with a known length or with your height before recording.",
  LOW_FRAME_RATE: `The video runs too slowly, or its frame times are too uneven, to follow a lift: it needs about ${MIN_RATE_HZ} frames per second or more.`,
  LANDMARK_LOST: `The wrist was lost in too many frames (more than ${percent(MAX_LOW_VISIBILITY_FRACTION)}), or frames arrived repeated or out of order.`,
  GAP_TOO_LONG: `The wrist was lost for more than ${MAX_GAP_S} s in one stretch.`,
  TOO_SHORT: `The recording is too short to analyse: it needs at least ${MIN_DURATION_S} s, and more than the filter needs to settle.`,
  NO_REPS: `No repetition was found: a rep is a lift of at least ${Math.round(MIN_PHASE_DISPLACEMENT_M * 100)} cm followed by a lowering, with the weight held still before and after.`,
};

export function refusalSentences(reasons: readonly RefusalReason[]): string[] {
  return reasons.map((r) => SENTENCES[r]);
}

/** The notes that go with one rep. Empty for an ordinary rep. */
export function repNotes(rep: RepResult): string[] {
  const notes: string[] = [];
  if (rep.filterLimited) notes.push("Too fast for the filter; work and peak force are under-read.");
  if (rep.trimmedRangeFraction < 0.9) notes.push(`Measured over ${percent(rep.trimmedRangeFraction)} of the detected movement.`);
  return notes;
}

// ---------------------------------------------------------------------------
// Scale
// ---------------------------------------------------------------------------

export type ScaleMethod =
  | { kind: "known-length"; lengthM: number; yA: number; yB: number }
  | { kind: "stature"; statureM: number; eyeY: number; ankleY: number };

export type ScaleOutcome = { ok: true; metersPerUnit: number; quantity: Quantity } | { ok: false; reason: string };

/**
 * What the capture view accepts, each limit defined once: the model refuses anything outside, and the view's
 * fields take their min, max and step from here. Judgement calls, set to catch a value typed in the wrong unit
 * (a height of 175, a ruler of 30) before it becomes a scale: a hand-held object from 5 cm to 3 m, a standing
 * person from 1 to 2.5 m, a weight a person can lift (0.1 to 500 kg), and the squat device's force range.
 */
export const CAPTURE_LIMITS = {
  knownLengthM: { min: 0.05, max: 3, step: 0.01 },
  statureM: { min: 1, max: 2.5, step: 0.01 },
  massKg: { min: 0.1, max: 500, step: 0.1 },
  deviceForceN: { ...DEVICE_FORCE_LIMITS_N, step: 10 },
} as const;

const within = (value: number, limits: { min: number; max: number }): boolean => Number.isFinite(value) && value >= limits.min && value <= limits.max;

/** Metres per frame height from the chosen method, tagged ESTIMATE, or the reason there is none. */
export function scaleFrom(method: ScaleMethod): ScaleOutcome {
  // A number above 0 that is outside the limits is most likely in centimetres; anything else falls to the reasons below.
  if (method.kind === "known-length" && method.lengthM > 0 && !within(method.lengthM, CAPTURE_LIMITS.knownLengthM)) {
    const { min, max } = CAPTURE_LIMITS.knownLengthM;
    return { ok: false, reason: `No scale from the known length: enter the length in metres, from ${min} to ${max} m (30 cm is 0.3).` };
  }
  if (method.kind === "stature" && method.statureM > 0 && !within(method.statureM, CAPTURE_LIMITS.statureM)) {
    const { min, max } = CAPTURE_LIMITS.statureM;
    return { ok: false, reason: `No scale from your height: enter your height in metres, from ${min} to ${max} m (175 cm is 1.75).` };
  }
  try {
    if (method.kind === "known-length") {
      const metersPerUnit = metersPerUnitFromKnownLength(method.lengthM, method.yA, method.yB);
      return {
        ok: true,
        metersPerUnit,
        quantity: derive(metersPerUnit, "m per frame height", "ESTIMATE", [], `From a known length of ${method.lengthM} m held at the wrist, the preferred method. ${SCALE_SENTENCE}`),
      };
    }
    const metersPerUnit = metersPerUnitFromStature(method.statureM, method.eyeY, method.ankleY);
    return {
      ok: true,
      metersPerUnit,
      quantity: derive(
        metersPerUnit,
        "m per frame height",
        "ESTIMATE",
        [],
        `From a stature of ${method.statureM} m and the eye and ankle in the frozen frame. Depth makes this method read high, by an estimated 5 to 10 %. ${SCALE_SENTENCE}`,
      ),
    };
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return {
      ok: false,
      reason:
        method.kind === "known-length"
          ? `No scale from the known length: enter a length above 0 and tap two ends at least ${percent(MIN_KNOWN_LENGTH_SPAN)} of the frame height apart.`
          : `No scale from your height: enter a height above 0, and stand upright side-on with the eye and the ankle visible, the ankle below the eye and at least ${percent(MIN_CALIBRATION_SPAN)} of the frame height apart.`,
    };
  }
}

/**
 * A known length gives a scale only from a frozen frame whose two ends were both set AFTER the freeze, with a
 * length above 0. Anything less would turn a slider's resting position into a scale.
 */
export function knownLengthReady(s: { frozen: boolean; endA: boolean; endB: boolean; lengthM: number }): boolean {
  return s.frozen && s.endA && s.endB && Number.isFinite(s.lengthM) && s.lengthM > 0;
}

/** The stature method needs a frozen frame, a pose read from that frame, and a height above 0. */
export function statureReady(s: { frozen: boolean; poseRead: boolean; statureM: number }): boolean {
  return s.frozen && s.poseRead && Number.isFinite(s.statureM) && s.statureM > 0;
}

// ---------------------------------------------------------------------------
// Inputs and analysis
// ---------------------------------------------------------------------------

export interface CaptureInputs {
  massKg: number;
  gEnvMs2: number;
  deviceForceN: number;
  metersPerUnit: number | null;
  /** How the scale was obtained, for the details of the set. */
  scaleNote?: string;
}

/** What is wrong with the inputs, in a sentence, or null. Check before analysing: bad inputs are programmer errors to the capture package. */
export function captureInputProblem(inputs: CaptureInputs): string | null {
  if (!Number.isFinite(inputs.massKg) || inputs.massKg <= 0) return "Enter the mass of the weight, above 0 kg.";
  if (!within(inputs.massKg, CAPTURE_LIMITS.massKg)) return `Enter the mass of the weight in kilograms, from ${CAPTURE_LIMITS.massKg.min} to ${CAPTURE_LIMITS.massKg.max} kg.`;
  if (!Number.isFinite(inputs.gEnvMs2) || inputs.gEnvMs2 < 0) return "The gravity of the environment must be 0 or more.";
  if (Number.isNaN(inputs.deviceForceN)) return "The device force is not a number: leave it empty for none, or enter newtons.";
  if (inputs.deviceForceN < 0) return "A device force must be 0 N or more.";
  if (!within(inputs.deviceForceN, CAPTURE_LIMITS.deviceForceN)) return `Enter the device force in newtons, from ${CAPTURE_LIMITS.deviceForceN.min} to ${CAPTURE_LIMITS.deviceForceN.max} N, or leave it empty for none.`;
  return null;
}

/** The optional device-force field: empty is none (0); anything the field cannot parse is NaN, never silently 0. */
export function parseDeviceForce(raw: string, badInput: boolean): number {
  if (badInput) return Number.NaN;
  return raw.trim() === "" ? 0 : Number(raw);
}

export interface RepRow {
  index: number; // 1-based
  rep: RepResult;
  notes: string[];
}

export type CaptureOutcome =
  | {
      kind: "analysed";
      session: SessionResult;
      reps: RepRow[];
      totalPositiveWorkJ: number;
      maxPeakForceN: number;
      confidence: Confidence;
      confidenceSentence: string;
      quality: QualityReport;
    }
  | { kind: "refused"; reasons: { code: RefusalReason; sentence: string }[] };

/** The scale's note, always ending with the sentence that it is the largest error, once. */
function scaleNote(note: string | undefined): string {
  const text = note && note.trim() !== "" ? note.trim() : "Calibration entered for this recording.";
  return text.includes(SCALE_SENTENCE) ? text : `${text} ${SCALE_SENTENCE}`;
}

/** Recorded frames and inputs in; a camera set, or a refusal with a sentence per reason and no numbers, out. */
export function analyseRecording(frames: readonly PoseFrame[], inputs: CaptureInputs, label: { id: string; title: string }): CaptureOutcome {
  const result = analyzeSession(frames, {
    massKg: inputs.massKg,
    gEnvMs2: inputs.gEnvMs2,
    deviceForceN: inputs.deviceForceN,
    metersPerUnit: inputs.metersPerUnit,
  });

  if (!result.ok) {
    return { kind: "refused", reasons: result.reasons.map((code) => ({ code, sentence: SENTENCES[code] })) };
  }

  const reps: RepRow[] = result.reps.map((rep, i) => ({ index: i + 1, rep, notes: repNotes(rep) }));
  const confidence = result.provenance.confidence;
  const fast = result.reps.filter((r) => r.filterLimited).length;
  const trimmed = result.reps.filter((r) => r.trimmedRangeFraction < 0.9).length;

  const mass = labelled("Mass of the weight", source(inputs.massKg, "kg", "MANUAL", "Entered. The tracked wrist stands in for the weight."));
  const gravity = labelled("Gravity", source(inputs.gEnvMs2, "m/s²", "MANUAL", "The environment the set was recorded in, chosen in the capture view."));
  const device = labelled("Device force", source(inputs.deviceForceN, "N", "MANUAL", "A constant device force resisting the lift, entered; 0 for a free weight."));
  const scale = labelled("Scale", derive(inputs.metersPerUnit as number, "m per frame height", "ESTIMATE", [], scaleNote(inputs.scaleNote)));
  const pipeline = (value: number, unit: string, note: string): Quantity => derive(value, unit, cameraPipelineTag(), [scale], note);

  const details: Detail[] = [
    mass,
    gravity,
    device,
    scale,
    labelled("Frame rate", source(result.quality.rateHz, "Hz", "MEASURED", "Median rate of the frames the video delivered.")),
    labelled("Frames lost", source(result.quality.lowVisibilityFraction * 100, "%", "MEASURED", "Frames in which the wrist was not visible.")),
    labelled("Reps detected", pipeline(reps.length, "reps", `Confidence ${confidence}. ${CONFIDENCE_SENTENCE}`)),
  ];
  if (fast > 0) {
    details.push(labelled("Reps too fast for the filter", pipeline(fast, "reps", `Shorter than ${FILTER_LIMITED_LIFT_S} s to lift: work and peak force are under-read for these reps.`)));
  }
  if (trimmed > 0) {
    details.push(labelled("Reps measured over part of the movement", pipeline(trimmed, "reps", "Less than 90 % of the detected movement was measured: the rest was taken for rest, a pick-up or a set-down.")));
  }

  return {
    kind: "analysed",
    session: cameraSession({
      id: label.id,
      title: label.title,
      reps: reps.length,
      totalPositiveWorkJ: result.totalPositiveWorkJ,
      maxPeakForceN: result.maxPeakForceN,
      inputs: [scale, mass, gravity, device],
      details,
    }),
    reps,
    totalPositiveWorkJ: result.totalPositiveWorkJ,
    maxPeakForceN: result.maxPeakForceN,
    confidence,
    confidenceSentence: `Confidence: ${confidence}. ${CONFIDENCE_SENTENCE}`,
    quality: result.quality,
  };
}
