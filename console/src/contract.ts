// Hub contract types (spec section 4, resolution sheet D2-D6, D9, D11, D13, D16-D18, NU1, NU5-NU10, M8).

export const INTAKE_INDS = [
  "intake_kcal",
  "intake_protein_g",
  "intake_carb_g",
  "intake_fat_g",
  "intake_water_ml",
  "intake_sodium_mg",
  "intake_potassium_mg",
  "intake_calcium_mg",
  "intake_iron_mg",
  "intake_vitd_ug",
] as const;
export type IntakeInd = (typeof INTAKE_INDS)[number];

export type Ind =
  | "hr"
  | "spo2"
  | "skin_temp"
  | "body_temp"
  | "bp_sys"
  | "bp_dia"
  | "glucose"
  | "sleep_h"
  | "mood"
  | "symptom"
  | "cabin_temp"
  | "cabin_rh"
  | "cabin_p"
  | "cabin_co2"
  | "cabin_lux"
  | "motion"
  | "load_raw"
  | "tilt"
  | "cabin_ppco2"
  | "space_weather"
  | "rad_dose_cum"
  | "body_mass"
  | IntakeInd;

export type SrcClass = "certified" | "hobby" | "self" | "nasa" | "replay";
export type QualityFlag =
  | "ok"
  | "motion"
  | "no_contact"
  | "settling"
  | "leads_off"
  | "out_of_range"
  | "assumed_pressure"
  | "stale";
export type Status = "ok" | "watch" | "act" | "unknown";
export type SourceKind = "nasa_std" | "clinical_ref" | "personal_baseline" | "team_convention" | "nasa_doc";
export type EscalateTo = "self" | "cmo" | "flight_surgeon";
export type CrewId = "crew-a" | "crew-b" | "crew-c";
export type SymptomCode = "headache" | "fatigue" | "nausea" | "poor_sleep" | "none";

export interface ReadingMessage {
  v: 1;
  node: string;
  boot: number;
  seq: number;
  age_ms: number;
  ind: Ind;
  val: number;
  unit: string;
  src: SrcClass;
  dev: string;
  q: QualityFlag[];
  crew?: CrewId;
  code?: SymptomCode;
}

// Picked on the camera page before a set (wrist-tracked vertical lifts). Older reps have none.
export type Exercise = "curl" | "overhead_press" | "row";

export interface RepMessage {
  v: 1;
  node: string;
  boot: number;
  seq: number;
  age_ms: number;
  type: "rep";
  session: string;
  rep: number;
  src: "camera" | "load_cell";
  peak_n: number;
  work_j: number;
  rom_m: number | null;
  g: number;
  mass_kg: number;
  t0_ms: number;
  t1_ms: number;
  exercise?: Exercise | null;
}

export interface AssessmentResult {
  ind: Ind;
  val: number;
  unit: string;
  status: Status;
  rule_id: string | null;
  source_kind: SourceKind | null;
  source_ref: string | null;
  guidance_id: string | null;
  escalate_to: EscalateTo;
  measured_at: string;
  crew: CrewId | null;
}

export type StatusEntry = AssessmentResult & {
  src: SrcClass;
  dev: string;
  q: QualityFlag[];
  node: string;
  reading_id: number;
};

export interface NodeState {
  node: string;
  online: boolean;
  last_seen: string | null;
}

export interface StatusBody {
  crew: CrewId | null;
  generated_at: string;
  nodes: NodeState[];
  results: StatusEntry[];
}

export type StoredReading = ReadingMessage & {
  id: number;
  measured_at: string;
  received_at: string;
  derived_from: number | null;
  mean_1h?: number | null; // with bucket_s, for an indicator judged on a 1-hour mean: the hub's mean at this row
};

export interface PostResult {
  id: number;
  measured_at: string;
  duplicate: boolean;
  results: StatusEntry[];
}

export interface Session {
  session: string;
  mass_kg: number;
  g: number;
  crew: CrewId | null;
  started_at: string;
  ended_at: string | null;
  camera_reps: number;
  load_cell_reps: number;
  exercise?: Exercise | null;
}

export type StoredRep = RepMessage & { id: number; measured_at: string };

export interface RepPair {
  rep: number;
  camera: StoredRep | null;
  load_cell: StoredRep | null;
  work_cell_j: number | null;
}

export interface RepsBody {
  session: string;
  pairs: RepPair[];
}

export interface Prompt {
  id: number;
  kind: "morning" | "post_exercise" | "cabin_trigger";
  asks: Ind[];
  crew: CrewId | null;
  status: "open" | "answered" | "skipped";
  created_at: string;
  trigger_reading_id: number | null;
  rule_id: string | null;
  trigger: StatusEntry | null;
}

export interface PromptAnswer {
  readings: ReadingMessage[];
  skipped?: boolean;
}

export interface PromptAnswerResult {
  prompt_id: number;
  reading_ids: number[];
  results: StatusEntry[];
}

export interface Alert {
  id: number;
  ind: Ind;
  status: Status;
  prev_status: Status | null;
  rule_id: string | null;
  measured_at: string;
  crew: CrewId | null;
  escalate_to: EscalateTo;
}

export interface LinkState {
  state: "contact" | "blackout" | "unreachable";
  light_time_s: number;
  time_scale: number;
  queue_len: number;
  last_blackout: { start: string; end: string | null } | null;
}

export type WsMessage =
  | { type: "snapshot"; data: StatusBody }
  | { type: "assessment"; data: StatusEntry }
  | { type: "alert"; data: Alert }
  | { type: "prompt"; data: Prompt }
  | { type: "link"; data: LinkState };

export interface SpaceWeather {
  status: Status;
  rule_id: string | null;
  reason: string;
  event_id: string | null;
  event_time: string | null;
  link: string | null;
  mode: "live" | "replay";
  cached_at: string | null;
  stale: boolean;
  route: string | null;
  events: object;
  ack: { crew: CrewId; at: string; event_id: string } | null;
  disclaimer: string;
}

export interface IssCabin {
  mode: "live" | "recorded";
  recorded_at: string | null;
  unit_note: string;
  items: {
    item: string;
    name: string;
    val: number;
    unit: string;
    val_hpa: number | null;
    measured_at: string;
    age_s: number;
    stale: boolean;
  }[];
}

export interface Summary {
  n: number;
  mean: number;
  min: number;
  max: number;
}

export interface IssReference {
  snapshot_date: string;
  mission: string;
  source_urls: string[];
  label: string;
  cabin: {
    temperature_c: Summary | null;
    rh_pct: Summary | null;
    co2_mmhg: Summary | null;
    co2_raw_unit: string | null;
  } | null;
  dose: {
    absorbed_mgy: number | null;
    absorbed_mgy_per_day: number | null;
    effective_msv: number | null;
    effective_msv_method: string | null;
    career_limit_msv: number | null;
    career_fraction: number | null;
    status: Status;
    profile: string | null;
    mission_day: number | null;
  };
}

type NutrientKey =
  | "kcal"
  | "protein_g"
  | "carb_g"
  | "fat_g"
  | "sodium_mg"
  | "potassium_mg"
  | "calcium_mg"
  | "iron_mg"
  | "vitd_ug";

export interface FoodItem {
  id: string;
  name: string;
  category: string;
  fdc_id: number;
  fdc_dataset: "foundation" | "sr_legacy";
  fdc_description: string;
  serving_g: number;
  serving_label: string;
  serving_source: string;
  fluid_ml_per_serving: number;
  fluid_basis: string;
  per100g: Record<NutrientKey, number | null>;
  kcal_basis: "measured_1008" | "atwater_general_2047" | "atwater_specific_2048";
  note: string;
}

export interface FoodCatalog {
  version: number;
  generated_at: string;
  generator: string;
  fdc_release: string;
  licence: string;
  disclaimer: string;
  nutrient_map: Record<string, number>;
  items: FoodItem[];
}

export interface FoodReference {
  ind: Ind;
  label: string;
  kind: "range" | "upper" | "floor" | "average" | "per_kg" | "text";
  low: number | null;
  high: number | null;
  unit: string;
  value_text: string;
  sex_note: string | null;
  source_ref: string;
  url: string;
  has_rule: boolean;
}

export interface FoodReferences {
  source: string;
  retrieved: string;
  items: FoodReference[];
  notes: string[];
}

export interface MealRequest {
  crew: CrewId | null;
  items: { food_id: string; servings: number }[];
  eaten_at?: string;
}

export interface MealResult {
  meal_id: number;
  readings: { ind: Ind; id: number; duplicate: boolean }[];
  not_reported: Ind[];
  results: StatusEntry[];
}

export interface NutrientTotal {
  val: number | null;
  meals_reporting: number;
  meals_total: number;
  status: Status;
  rule_id: string | null;
  source_kind: SourceKind | null;
  source_ref: string | null;
  escalate_to: EscalateTo;
  floor_judged: boolean | null;
}

export interface FoodDay {
  crew: CrewId | null;
  window_start: string;
  window_end: string;
  totals: Record<IntakeInd, NutrientTotal>;
  meals: {
    meal_id: number;
    eaten_at: string;
    crew: CrewId | null;
    items: { food_id: string; servings: number }[];
  }[];
  body_mass: number | null;
}

export interface ExerciseDay {
  window_start: string;
  window_end: string;
  sessions: number;
  camera_reps: number;
  camera_work_j: number | null;
  cell_work_j: number | null;
  replay: boolean;
  excluded_reps: number;
}
