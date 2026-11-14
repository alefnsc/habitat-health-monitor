/**
 * Preset sessions: pure functions (person, environment, parameters) -> SessionResult.
 *
 * Every number comes back as a Quantity with its provenance tag and a note, so a view
 * never has to invent a source. A number that cannot be computed honestly is `null`, with
 * the reason in the note. Formulas are docs/strategy.md §2; the arithmetic lives in
 * @ground-truth/physics wherever it exists there.
 *
 * Tag order, from the least to the most assumed (used when a total mixes tags): see
 * `weakestTag`.
 */

import { VALIDATED_ON_REAL_VIDEO } from "@ground-truth/capture";
import {
  G_ENV_MS2,
  GENC_2010_PEAK_LOAD_DECREMENT,
  STANDARD_GRAVITY_MS2,
  ergometerWorkJ,
  froudeTransitionSpeedMs,
  metabolicRange,
  totalForceN,
  treadmillEffectiveForceN,
  deviceForceForEarthEquivalenceN,
  type Body,
  type LoadBout,
} from "@ground-truth/physics";

export type Tag = "MEASURED" | "MANUAL" | "MODEL" | "ASSUMPTION" | "CALIBRATED" | "ESTIMATE";

/** `value` null means not computable; the note then says why. Otherwise the note says where the number comes from. */
export interface Quantity {
  value: number | null;
  unit: string;
  tag: Tag;
  note: string;
}

/** A Quantity shown in a session's expandable details. The label is the only addition to the plan's Quantity. */
export interface Detail extends Quantity {
  label: string;
}

export interface SessionResult {
  id: string;
  title: string;
  energy: Quantity; // mechanical work, J
  peakLoad: Quantity; // N
  bout: LoadBout | null; // null when the session has no skeletal load term in this model
  /** The quantities the bout's peak and cycle count come from, so the day's stimulus takes their tags. Empty when `bout` is null. */
  boutInputs: Quantity[];
  details: Detail[]; // parameters and intermediate values shown on expand
}

export interface Person {
  massKg: number;
  legLengthM: number;
}

/** The person the demo starts with: 78.4 kg (the brief's example mass) and a 0.9 m leg. */
export const DEFAULT_PERSON: Person = { massKg: 78.4, legLengthM: 0.9 };

export interface Env {
  body: Body;
  gEnvMs2: number;
}

export const EARTH_ENV: Env = { body: "EARTH", gEnvMs2: G_ENV_MS2.EARTH };

/** The environments of the demo's selector, plus TRANSIT (reachable from the model, not from the selector). */
export const ENVS: Readonly<Record<Body, Env>> = {
  EARTH: EARTH_ENV,
  MOON: { body: "MOON", gEnvMs2: G_ENV_MS2.MOON },
  MARS: { body: "MARS", gEnvMs2: G_ENV_MS2.MARS },
  ISS: { body: "ISS", gEnvMs2: G_ENV_MS2.ISS },
  TRANSIT: { body: "TRANSIT", gEnvMs2: G_ENV_MS2.TRANSIT },
};

// ---------------------------------------------------------------------------
// Tags. A number is no more certain than its least certain input.
// ---------------------------------------------------------------------------

/**
 * Strongest to weakest, following the physics README ("Measured versus estimated"): numbers computed from
 * the inputs, then a published model with stated parameters, then calibrated or estimated, then a parameter
 * this demo chose.
 */
const TAG_ORDER: readonly Tag[] = ["MEASURED", "MANUAL", "MODEL", "CALIBRATED", "ESTIMATE", "ASSUMPTION"];

/** The weakest (least certain) of the tags. An empty list is MODEL. */
export function weakestTag(tags: readonly Tag[]): Tag {
  let worst = -1;
  for (const tag of tags) worst = Math.max(worst, TAG_ORDER.indexOf(tag));
  return worst < 0 ? "MODEL" : (TAG_ORDER[worst] as Tag);
}

/** The tag of a formula step. `EXACT` is plain arithmetic: it adds no uncertainty of its own, only its inputs'. */
export type Formula = Tag | "EXACT";

/**
 * A value that is entered, chosen by this demo, or measured: it has no inputs, so its tag is typed here. Use
 * `derive` for anything computed from other quantities.
 */
export function source(value: number | null, unit: string, tag: Tag, note: string): Quantity {
  return { value, unit, tag, note };
}

/**
 * A value computed from other quantities. Its tag is the weakest of the formula's own tag and every input's, so a
 * derived tag cannot be written by hand. An EXACT formula needs at least one input (there would be nothing to take a
 * tag from). `value` null means not computable, and the note then says why.
 */
export function derive(value: number | null, unit: string, formula: Formula, inputs: readonly Quantity[], note: string): Quantity {
  if (note.trim() === "") throw new RangeError("a derived quantity needs a note");
  if (formula === "EXACT" && inputs.length === 0) throw new RangeError("an EXACT formula needs at least one input to take its tag from");
  const tags = inputs.map((q) => q.tag);
  if (formula !== "EXACT") tags.push(formula);
  return { value, unit, tag: weakestTag(tags), note };
}

/** A labelled copy of a quantity, for a session's details. */
export function labelled(label: string, q: Quantity): Detail {
  return { label, ...q };
}

// ---------------------------------------------------------------------------
// Parameters. Every one is exported with its tag and source.
// ---------------------------------------------------------------------------

export interface TreadmillParams {
  durationS: number;
  cadenceStepsPerMin: number;
  comVerticalM: number;
  earthPeakMultiplier: number;
  supportFraction: number;
}

export const TREADMILL_DEFAULTS: Readonly<TreadmillParams> = {
  /** MANUAL: session length, an entry. 30 minutes. */
  durationS: 1800,
  /** ASSUMPTION (this demo's choice): 170 steps/min, a common running cadence. Not measured on anyone. */
  cadenceStepsPerMin: 170,
  /** ASSUMPTION: vertical travel of the centre of mass per step, 0.08 m. Brief §2 gives W_per_step ≈ F_eff · Δz_COM but no Δz_COM. */
  comVerticalM: 0.08,
  /** ASSUMPTION: peak vertical ground reaction force in running as a multiple of body weight; 2 to 3 body weights is commonly cited, 2.5 is the middle. */
  earthPeakMultiplier: 2.5,
  /** MANUAL (a device setting; brief §2, subject load device at 70 % of 1 g body weight). Used on the ISS only. */
  supportFraction: 0.7,
};

export interface SquatParams {
  deviceForceN: number;
  sets: number;
  repsPerSet: number;
  strokeM: number;
  replaceBodyWeight: boolean;
}

export const SQUAT_DEFAULTS: Readonly<SquatParams> = {
  /** MANUAL: the force set on the device, 1000 N. */
  deviceForceN: 1000,
  /** MANUAL: 3 sets. */
  sets: 3,
  /** MANUAL: 12 reps per set (brief §2's example set). */
  repsPerSet: 12,
  /** MANUAL: 0.5 m stroke. */
  strokeM: 0.5,
  /** When true, the device force is raised so the total matches the same setting on Earth (brief §2, body-weight replacement). */
  replaceBodyWeight: false,
};

export interface CycleParams {
  durationS: number;
  displayedPowerW: number;
}

export const CYCLE_DEFAULTS: Readonly<CycleParams> = {
  /** MANUAL: 45 minutes (brief §10's session). */
  durationS: 2700,
  /** MANUAL: 150 W as shown on the ergometer's display. */
  displayedPowerW: 150,
};

export type PresetKind = "treadmill" | "squats" | "cycle";

export type ParamField =
  | { kind: "number"; key: string; label: string; unit: string; min: number; max: number; step: number; whole?: true }
  | { kind: "boolean"; key: string; label: string };

/** What a view may edit, and within which limits. Data only. */
/** The range of a constant device force, newtons: the squat device here and the device force of a camera set. */
export const DEVICE_FORCE_LIMITS_N = { min: 0, max: 5000 } as const;

export const PARAM_FIELDS: Readonly<Record<PresetKind, readonly ParamField[]>> = {
  treadmill: [
    { kind: "number", key: "durationS", label: "Duration", unit: "s", min: 60, max: 7200, step: 60 },
    { kind: "number", key: "cadenceStepsPerMin", label: "Cadence", unit: "steps/min", min: 100, max: 220, step: 1 },
    { kind: "number", key: "comVerticalM", label: "Vertical travel of the centre of mass per step", unit: "m", min: 0.01, max: 0.2, step: 0.005 },
    { kind: "number", key: "earthPeakMultiplier", label: "Earth peak force", unit: "× body weight", min: 1, max: 4, step: 0.1 },
    { kind: "number", key: "supportFraction", label: "Harness load (ISS only)", unit: "× 1 g body weight", min: 0, max: 1, step: 0.05 },
  ],
  squats: [
    { kind: "number", key: "deviceForceN", label: "Device force", unit: "N", ...DEVICE_FORCE_LIMITS_N, step: 50 },
    { kind: "number", key: "sets", label: "Sets", unit: "", min: 1, max: 10, step: 1, whole: true },
    { kind: "number", key: "repsPerSet", label: "Reps per set", unit: "", min: 1, max: 30, step: 1, whole: true },
    { kind: "number", key: "strokeM", label: "Stroke", unit: "m", min: 0.1, max: 1, step: 0.05 },
    { kind: "boolean", key: "replaceBodyWeight", label: "Add the body weight the environment lacks" },
  ],
  cycle: [
    { kind: "number", key: "durationS", label: "Duration", unit: "s", min: 60, max: 7200, step: 60 },
    { kind: "number", key: "displayedPowerW", label: "Displayed power", unit: "W", min: 20, max: 400, step: 5 },
  ],
};

// ---------------------------------------------------------------------------
// Validation: programmer errors throw. A view clamps its inputs before calling.
// ---------------------------------------------------------------------------

function requirePositiveFinite(name: string, value: number): void {
  if (!Number.isFinite(value) || value <= 0) throw new RangeError(`${name} must be a finite number > 0, got ${value}`);
}

function requireWholeNumber(name: string, value: number): void {
  if (!Number.isInteger(value) || value < 1) throw new RangeError(`${name} must be a whole number >= 1, got ${value}`);
}

export function validatePerson(person: Person): void {
  requirePositiveFinite("massKg", person.massKg);
  requirePositiveFinite("legLengthM", person.legLengthM);
}

// ---------------------------------------------------------------------------
// Inputs common to every preset
// ---------------------------------------------------------------------------

const massOf = (person: Person): Detail => labelled("Body mass", source(person.massKg, "kg", "MANUAL", "Entered."));
const gravityOf = (env: Env): Detail => labelled("Gravity", source(env.gEnvMs2, "m/s²", "MODEL", "Gravity of the environment (brief §2); about 0 on the ISS."));

// ---------------------------------------------------------------------------
// Treadmill run
// ---------------------------------------------------------------------------

export function treadmillRun(person: Person, env: Env, p: TreadmillParams = TREADMILL_DEFAULTS): SessionResult {
  validatePerson(person);
  requirePositiveFinite("durationS", p.durationS);
  requirePositiveFinite("cadenceStepsPerMin", p.cadenceStepsPerMin);
  requirePositiveFinite("comVerticalM", p.comVerticalM);
  requirePositiveFinite("earthPeakMultiplier", p.earthPeakMultiplier);
  if (!Number.isFinite(p.supportFraction) || p.supportFraction < 0 || p.supportFraction > 1) {
    throw new RangeError(`supportFraction must be within [0, 1], got ${p.supportFraction}`);
  }

  const onIss = env.body === "ISS";
  const mass = massOf(person);
  const gravity = gravityOf(env);
  const duration = labelled("Duration", source(p.durationS, "s", "MANUAL", "Session length, entered."));
  const cadence = labelled("Cadence", source(p.cadenceStepsPerMin, "steps/min", "ASSUMPTION", "Chosen by this demo; not measured on anyone."));
  const rise = labelled(
    "Vertical travel of the centre of mass per step",
    source(p.comVerticalM, "m", "ASSUMPTION", "Chosen by this demo; the brief gives the formula but no value."),
  );
  const multiple = labelled(
    "Earth peak force",
    source(p.earthPeakMultiplier, "× body weight", "ASSUMPTION", "Running peak vertical force is commonly cited at 2 to 3 body weights; this demo takes 2.5."),
  );
  const harness = labelled(
    "Harness load",
    source(
      p.supportFraction,
      "× 1 g body weight",
      "MANUAL",
      onIss ? "Subject load device setting, applied here (ISS)." : "Subject load device setting; used on the ISS only, not applied in this environment.",
    ),
  );

  const steps = labelled("Steps", derive((p.durationS / 60) * p.cadenceStepsPerMin, "steps", "EXACT", [duration, cadence], "Duration × cadence."));
  const strikes = labelled(
    "Loading cycles, one leg",
    derive((steps.value as number) / 2, "cycles", "ASSUMPTION", [steps], "One foot strike per stride on a given leg: half the steps. The load stimulus counts cycles at one site."),
  );
  const harnessFraction = onIss ? p.supportFraction : 0;
  const fEffN = treadmillEffectiveForceN(person.massKg, env.gEnvMs2, harnessFraction);
  const fEff = labelled(
    "Effective force",
    derive(
      fEffN,
      "N",
      "MODEL",
      onIss ? [mass, gravity, harness] : [mass, gravity],
      onIss ? "F_eff = m · g_env + harness load × m · 1 g (brief §2). A static model, not a measured ground reaction force." : "F_eff = m · g_env (brief §2). A static model, not a measured ground reaction force.",
    ),
  );
  // On the T2 treadmill the relevant gravity for gait is the harness-supplied one, not the cabin's 0 (physics README).
  const gaitG = onIss ? p.supportFraction * STANDARD_GRAVITY_MS2 : env.gEnvMs2;
  const transition = labelled(
    "Walk-run transition speed",
    derive(
      froudeTransitionSpeedMs(gaitG, person.legLengthM),
      "m/s",
      "MODEL",
      onIss ? [harness] : [gravity],
      onIss ? "√(Fr · g · L) with Fr = 0.5 and g the harness-supplied gravity (brief §2)." : "√(Fr · g · L) with Fr = 0.5 (brief §2). Gait does not scale linearly between gravities.",
    ),
  );

  const details: Detail[] = [duration, cadence, steps, rise, multiple, harness, fEff, strikes, transition];
  if (onIss) {
    details.push(labelled("Static peak, for comparison", derive(p.earthPeakMultiplier * fEffN, "N", "ASSUMPTION", [multiple, fEff], "The peak if it scaled with the effective force (2.5 × F_eff), as it does in the other environments. It follows the harness field; the decrement-based peak above does not.")));
  }

  if (!(fEffN > 0)) {
    const reason = "A treadmill session is not possible here: no gravity presses the foot to the belt and no harness load is applied.";
    return {
      id: "treadmill",
      title: "Treadmill run",
      energy: derive(null, "J", "MODEL", [mass, gravity], reason),
      peakLoad: derive(null, "N", "MODEL", [mass, gravity], reason),
      bout: null,
      boutInputs: [],
      details,
    };
  }

  const energy = derive(
    (steps.value as number) * fEffN * p.comVerticalM,
    "J",
    "MODEL",
    [steps, fEff, rise],
    "Steps × F_eff × vertical travel of the centre of mass per step (brief §2). Mechanical work only, not metabolic energy. Rests on two ASSUMPTION parameters: cadence and vertical travel.",
  );

  const earthBodyWeightN = person.massKg * STANDARD_GRAVITY_MS2;
  const peakLoad = onIss
    ? derive(
        p.earthPeakMultiplier * earthBodyWeightN * (1 - GENC_2010_PEAK_LOAD_DECREMENT.running),
        "N",
        "MODEL",
        [multiple, mass],
        "The Earth peak (an ASSUMPTION multiple of body weight) reduced by the measured on-orbit decrement for running, 75 % (Genc 2010), even at maximum device settings. The decrement was measured at maximum device settings, so this peak does not vary with the harness field and does not follow the effective force.",
      )
    : derive(
        p.earthPeakMultiplier * fEffN,
        "N",
        "ASSUMPTION",
        [multiple, fEff],
        "Peak assumed to scale with the effective weight. Partial-gravity running is not a scaled copy of Earth running, so treat this as indicative.",
      );

  return { id: "treadmill", title: "Treadmill run", energy, peakLoad, bout: { cycles: strikes.value as number, peakLoad: peakLoad.value as number }, boutInputs: [peakLoad, strikes], details };
}

// ---------------------------------------------------------------------------
// Resistive squats
// ---------------------------------------------------------------------------

export function resistiveSquats(person: Person, env: Env, p: SquatParams = SQUAT_DEFAULTS): SessionResult {
  validatePerson(person);
  if (!Number.isFinite(p.deviceForceN) || p.deviceForceN < 0) throw new RangeError(`deviceForceN must be a finite number >= 0, got ${p.deviceForceN}`);
  requireWholeNumber("sets", p.sets);
  requireWholeNumber("repsPerSet", p.repsPerSet);
  requirePositiveFinite("strokeM", p.strokeM);

  const mass = massOf(person);
  const gravity = gravityOf(env);
  const set = labelled("Device force set", source(p.deviceForceN, "N", "MANUAL", "Entered."));
  const reps = labelled("Sets × reps", source(p.sets * p.repsPerSet, "reps", "MANUAL", `${p.sets} sets of ${p.repsPerSet}, entered.`));
  const stroke = labelled("Stroke", source(p.strokeM, "m", "MANUAL", "Entered."));

  // Body-weight replacement: the setting is a target for the total on Earth; the device supplies what the environment does not.
  const deviceN = p.replaceBodyWeight
    ? deviceForceForEarthEquivalenceN(p.deviceForceN + person.massKg * STANDARD_GRAVITY_MS2, person.massKg, env.gEnvMs2)
    : p.deviceForceN;
  const applied = labelled(
    "Device force applied",
    p.replaceBodyWeight
      ? derive(deviceN, "N", "MODEL", [set, mass, gravity], "F_device = F_target − m · g_env, with the target the setting plus the full Earth body weight (brief §2).")
      : derive(deviceN, "N", "EXACT", [set], "As entered; the body weight the environment lacks is not added."),
  );
  const bodyWeight = labelled("Body weight in this environment", derive(person.massKg * env.gEnvMs2, "N", "MODEL", [mass, gravity], "m · g_env."));
  const totalN = totalForceN(deviceN, person.massKg, env.gEnvMs2);
  const total = labelled("Total force", derive(totalN, "N", "MODEL", [applied, bodyWeight], "F_total = F_device + m · g_env (brief §2). Static: the inertial term is not included."));
  const cycles = labelled("Loading cycles", derive(reps.value as number, "cycles", "EXACT", [reps], "One per rep, on each leg."));
  // The run's bout is the force through one leg; the squat's total force goes through both, so the bout takes half of it.
  const perLeg = labelled(
    "Peak load, one leg",
    derive(totalN / 2, "N", "ASSUMPTION", [total], "Half the total force: the load is assumed to be shared equally between both legs. The daily load stimulus counts one leg for every session, so the squats are on the same per-leg basis as the run."),
  );
  const wholeBody = labelled(
    "Whole body moved through the stroke",
    source(1, "", "ASSUMPTION", "The energy takes the total force, which includes the body's weight, over the full stroke: the whole body mass is assumed to rise by the stroke each rep. The body's centre of mass travels less than the bar in a real squat."),
  );

  const peakLoad = derive(totalN, "N", "MODEL", [total], "Total force F_device + m · g_env (brief §2), through both legs. Static: the inertial term of the movement is not included, so a fast rep loads more than this.");
  const energy = derive(
    (reps.value as number) * totalN * p.strokeM,
    "J",
    "MODEL",
    [reps, total, stroke, wholeBody],
    "Reps × total force × stroke: concentric work only, force taken as constant over the stroke (brief §2), the whole body moved through the full stroke (an assumption).",
  );
  return {
    id: "squats",
    title: "Resistive squats",
    energy,
    peakLoad,
    bout: { cycles: cycles.value as number, peakLoad: perLeg.value as number },
    boutInputs: [perLeg, cycles],
    details: [set, reps, stroke, applied, bodyWeight, total, perLeg, cycles, wholeBody],
  };
}

// ---------------------------------------------------------------------------
// Cycle ergometer
// ---------------------------------------------------------------------------

export function cycleErgometer(person: Person, _env: Env, p: CycleParams = CYCLE_DEFAULTS): SessionResult {
  validatePerson(person);
  requirePositiveFinite("durationS", p.durationS);
  requirePositiveFinite("displayedPowerW", p.displayedPowerW);

  const duration = labelled("Duration", source(p.durationS, "s", "MANUAL", "Entered."));
  const power = labelled("Displayed power", source(p.displayedPowerW, "W", "MANUAL", "As shown on the ergometer's display."));
  const workJ = ergometerWorkJ([
    { tS: 0, displayedPowerW: p.displayedPowerW },
    { tS: p.durationS, displayedPowerW: p.displayedPowerW },
  ]);
  const energy = derive(
    workJ,
    "J",
    "MODEL",
    [duration, power],
    "Displayed power corrected with the CEVIS dynamometer relation, P = 0.98 · displayed − 11.8 W (NASA/TP-2007-214760), integrated over the session. Same in every environment.",
  );
  const met = metabolicRange(workJ);

  return {
    id: "cycle",
    title: "Cycle ergometer",
    energy,
    peakLoad: derive(null, "N", "MODEL", [], "No skeletal load term in this model: the ergometer's resistance is not modelled as a peak force through the skeleton."),
    bout: null,
    boutInputs: [],
    details: [
      duration,
      power,
      labelled("Metabolic cost, lower bound", derive(met.lowJ, "J", "ESTIMATE", [energy], `Work ÷ 0.25. ${met.basis}. A range, never a single figure.`)),
      labelled("Metabolic cost, upper bound", derive(met.highJ, "J", "ESTIMATE", [energy], `Work ÷ 0.20. ${met.basis}. A range, never a single figure.`)),
    ],
  };
}

// ---------------------------------------------------------------------------
// Camera set
// ---------------------------------------------------------------------------

/**
 * The tag of the camera pipeline as a formula step: ESTIMATE while the capture package says it has not been
 * validated on real video, MEASURED once it has. Read from that package's constant, never duplicated.
 */
export function cameraPipelineTag(): Tag {
  return VALIDATED_ON_REAL_VIDEO ? "MEASURED" : "ESTIMATE";
}

/** What a camera set's peak force is, and is not. Shown on its card and in its note. */
export const CAMERA_PEAK_SCOPE = "The force on the weight, not through the skeleton; it excludes body weight.";

export interface CameraSetInput {
  id: string;
  title: string;
  reps: number;
  totalPositiveWorkJ: number;
  maxPeakForceN: number;
  /** What the numbers rest on (scale, mass, gravity, device force), so the tags can follow. Built by the capture flow. */
  inputs: readonly Quantity[];
  /** Shown on expand: scale, mass, environment, confidence, per-set flags. Built by the capture flow. */
  details: Detail[];
}

/**
 * A set measured from a camera or a video file. Energy and peak load are no more certain than the unvalidated
 * pipeline and the scale (ESTIMATE). The set is a record of a real lift in the environment it was recorded in,
 * so it is the same in every environment of the selector: it is not re-scaled. It adds energy to the day and
 * nothing to the load stimulus.
 */
export function cameraSession(set: CameraSetInput): SessionResult {
  const energy = derive(
    set.totalPositiveWorkJ,
    "J",
    cameraPipelineTag(),
    set.inputs,
    "Positive work of the tracked wrist over the detected reps, from a camera or video file. Scale is the largest error. Not validated on real video.",
  );
  const peakLoad = derive(
    set.maxPeakForceN,
    "N",
    cameraPipelineTag(),
    set.inputs,
    `Largest peak force over the reps, from second differences of the filtered wrist position. ${CAMERA_PEAK_SCOPE} The noisiest output: indicative only. Not validated on real video.`,
  );
  return {
    id: set.id,
    title: set.title,
    energy,
    peakLoad,
    // No bout: the load stimulus is defined on the force through the skeleton, and this peak is the force on the weight.
    bout: null,
    boutInputs: [],
    details: set.details,
  };
}

// ---------------------------------------------------------------------------
// Peak load in multiples of Earth body weight
// ---------------------------------------------------------------------------

/** A session's peak load as a multiple of the person's body weight on Earth (m · 9.81), with the weakest tag of the peak load and the mass. */
export function peakInBodyWeights(session: SessionResult, person: Person): Quantity {
  validatePerson(person);
  const unit = "× Earth body weight";
  const mass = massOf(person);
  if (session.peakLoad.value === null) return derive(null, unit, "EXACT", [session.peakLoad, mass], session.peakLoad.note);
  return derive(
    session.peakLoad.value / (person.massKg * STANDARD_GRAVITY_MS2),
    unit,
    "EXACT",
    [session.peakLoad, mass],
    "Peak load divided by this person's body weight on Earth (m · 9.81 m/s²). Same source as the peak load.",
  );
}
