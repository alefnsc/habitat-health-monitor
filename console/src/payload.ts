import type { CrewId, Ind, ReadingMessage, SymptomCode } from "./contract";

export type ManualInd = "hr" | "spo2" | "body_temp" | "bp_sys" | "bp_dia" | "glucose" | "sleep_h" | "mood" | "body_mass";

export const UNITS: Record<Ind, string> = {
  hr: "bpm",
  spo2: "%",
  skin_temp: "C",
  body_temp: "C",
  bp_sys: "mmHg",
  bp_dia: "mmHg",
  glucose: "mg/dL",
  sleep_h: "h",
  mood: "1-5",
  symptom: "code",
  cabin_temp: "C",
  cabin_rh: "%",
  cabin_p: "hPa",
  cabin_co2: "ppm",
  cabin_lux: "lx",
  motion: "g",
  load_raw: "N",
  tilt: "state",
  cabin_ppco2: "mmHg",
  space_weather: "level",
  rad_dose_cum: "mSv",
  intake_kcal: "kcal",
  intake_protein_g: "g",
  intake_carb_g: "g",
  intake_fat_g: "g",
  intake_water_ml: "mL",
  intake_sodium_mg: "mg",
  intake_potassium_mg: "mg",
  intake_calcium_mg: "mg",
  intake_iron_mg: "mg",
  intake_vitd_ug: "ug",
  body_mass: "kg",
};

// Sanity limits for typing errors, not health thresholds. Judging stays with the hub.
export const ENTRY_BOUNDS: Record<ManualInd, { min: number; max: number; step: number }> = {
  hr: { min: 20, max: 250, step: 1 },
  spo2: { min: 50, max: 100, step: 1 },
  body_temp: { min: 30.0, max: 45.0, step: 0.1 },
  bp_sys: { min: 60, max: 260, step: 1 },
  bp_dia: { min: 30, max: 160, step: 1 },
  glucose: { min: 20, max: 600, step: 1 },
  sleep_h: { min: 0, max: 24, step: 0.25 },
  mood: { min: 1, max: 5, step: 1 },
  body_mass: { min: 20, max: 300, step: 0.1 },
};

const LABELS: Record<ManualInd, string> = {
  hr: "Heart rate",
  spo2: "SpO2",
  body_temp: "Body temperature",
  bp_sys: "Systolic",
  bp_dia: "Diastolic",
  glucose: "Glucose",
  sleep_h: "Sleep",
  mood: "Mood",
  body_mass: "Body mass",
};

export type ManualInput =
  | { ind: "hr" | "spo2" | "body_temp" | "glucose" | "sleep_h" | "mood" | "body_mass"; val: number }
  | { ind: "bp"; sys: number; dia: number }
  | { ind: "symptom"; codes: SymptomCode[] };

export interface Sequencer {
  next(): number;
  boot: number;
}

export function createSequencer(bootEpochS: number): Sequencer {
  let n = 0;
  return { boot: bootEpochS, next: () => ++n };
}

type BuildResult = { ok: true; messages: ReadingMessage[] } | { ok: false; error: string };

function boundsError(ind: ManualInd, val: number): string | null {
  if (!Number.isFinite(val)) return `${LABELS[ind]} must be a number.`;
  const b = ENTRY_BOUNDS[ind];
  if (val < b.min || val > b.max) return `${LABELS[ind]} must be ${b.min} to ${b.max} ${UNITS[ind]}.`;
  return null;
}

export function buildManualReadings(
  input: ManualInput,
  crew: CrewId,
  src: "certified" | "self",
  seq: Sequencer,
): BuildResult {
  const make = (ind: Ind, val: number, s: "certified" | "self", code?: SymptomCode): ReadingMessage => {
    const m: ReadingMessage = {
      v: 1,
      node: "manual",
      boot: seq.boot,
      seq: seq.next(),
      age_ms: 0,
      ind,
      val,
      unit: UNITS[ind],
      src: s,
      dev: "manual",
      q: ["ok"],
      crew,
    };
    if (code) m.code = code;
    return m;
  };

  if (input.ind === "bp") {
    const e = boundsError("bp_sys", input.sys) ?? boundsError("bp_dia", input.dia);
    if (e) return { ok: false, error: e };
    if (input.sys <= input.dia) return { ok: false, error: "Systolic must be higher than diastolic." };
    return { ok: true, messages: [make("bp_sys", input.sys, src), make("bp_dia", input.dia, src)] };
  }
  if (input.ind === "symptom") {
    const codes = input.codes;
    if (codes.length === 0) return { ok: false, error: "Pick at least one option, or None." };
    if (codes.includes("none") && codes.length > 1) {
      return { ok: false, error: "None cannot be combined with a symptom." };
    }
    return { ok: true, messages: codes.map((c) => make("symptom", 1, "self", c)) };
  }
  if (input.ind === "mood") {
    if (!Number.isInteger(input.val) || input.val < 1 || input.val > 5) {
      return { ok: false, error: "Mood must be a whole number from 1 to 5." };
    }
    return { ok: true, messages: [make("mood", input.val, "self")] };
  }
  const e = boundsError(input.ind, input.val);
  if (e) return { ok: false, error: e };
  const s = input.ind === "sleep_h" ? "self" : src;
  return { ok: true, messages: [make(input.ind, input.val, s)] };
}
