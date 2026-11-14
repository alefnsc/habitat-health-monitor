import { describe, expect, it } from "vitest";
import type { PoseFrame, RepResult } from "@ground-truth/capture";
import { legSession, syntheticSession } from "../../vendor/ground-truth/capture/test/helpers";
import {
  CAPTURE_LIMITS,
  CONFIDENCE_SENTENCE,
  SCALE_SENTENCE,
  analyseRecording,
  captureInputProblem,
  createGate,
  timingProblem,
  knownLengthReady,
  parseDeviceForce,
  refusalSentences,
  repNotes,
  scaleFrom,
  statureReady,
  transition,
  type CaptureInputs,
  type FlowEvent,
  type FlowState,
} from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { PARAM_FIELDS } from "../../vendor/ground-truth/demo/src/model/scenarios";

/*
 * Synthetic lifts: a 10 kg load, 0.5 m minimum-jerk lifts of 1 s with 1 s lowerings and rests, 60 Hz, Earth,
 * 2.5 m per frame height. Hand-derived truth per rep:
 *   positive work = m g h = 10 × 9.81 × 0.5 = 49.05 J, so three reps = 147.15 J
 *   peak force    = m (g + a_peak), a_peak = (10 / √3) h / T² = 5.7735 × 0.5 / 1² = 2.8868 m/s²,
 *                   so 10 × (9.81 + 2.8868) = 126.97 N
 * The capture package trims the window and filters at 4 Hz, which costs about 0.5 % of work; the checks
 * below allow 3 %. The numbers are not read off the code.
 */
const lift = { reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 1, rateHz: 60, noiseM: 0, seed: 1, metersPerUnit: 2.5 };
const earth: CaptureInputs = { massKg: 10, gEnvMs2: 9.81, deviceForceN: 0, metersPerUnit: 2.5 };
const label = { id: "camera-1", title: "Camera set" };

describe("flow state machine", () => {
  const path: [FlowState, FlowEvent, FlowState][] = [
    ["idle", "openSource", "calibrating"],
    ["calibrating", "calibrated", "ready"],
    ["ready", "recalibrate", "calibrating"],
    ["ready", "start", "recording"],
    ["recording", "analysed", "analysed"],
    ["recording", "refused", "refused"],
    ["analysed", "openSource", "calibrating"],
    ["refused", "openSource", "calibrating"],
    ["recording", "failed", "failed"],
    ["failed", "openSource", "calibrating"],
  ];
  it.each(path)("%s --%s--> %s", (from, event, to) => {
    expect(transition(from, event)).toBe(to);
  });

  it("reset returns to idle from anywhere", () => {
    for (const s of ["idle", "calibrating", "ready", "recording", "analysed", "refused", "failed"] as const) {
      expect(transition(s, "reset")).toBe("idle");
    }
  });

  it("an event that does not apply leaves the state alone (no recording before a scale, no stop when not recording)", () => {
    expect(transition("idle", "start")).toBe("idle");
    expect(transition("calibrating", "start")).toBe("calibrating");
    expect(transition("ready", "analysed")).toBe("ready");
    expect(transition("analysed", "start")).toBe("analysed");
    expect(transition("ready", "failed")).toBe("ready"); // only a recording can fail
    expect(transition("failed", "start")).toBe("failed");
  });

  it("walks idle to analysed", () => {
    const events: FlowEvent[] = ["openSource", "calibrated", "start", "analysed"];
    expect(events.reduce<FlowState>((s, e) => transition(s, e), "idle")).toBe("analysed");
  });
});

describe("scale", () => {
  it("known length: 0.30 m over a span of 0.30 of the frame is 1.0 m per frame height, tagged ESTIMATE", () => {
    const s = scaleFrom({ kind: "known-length", lengthM: 0.3, yA: 0.4, yB: 0.7 });
    expect(s.ok).toBe(true);
    if (!s.ok) return;
    expect(s.metersPerUnit).toBeCloseTo(1.0, 12);
    expect(s.quantity.tag).toBe("ESTIMATE");
    expect(s.quantity.value).toBeCloseTo(1.0, 12);
    expect(s.quantity.note).toContain(SCALE_SENTENCE);
    expect(s.quantity.note).toMatch(/known length/i);
  });

  it("stature: 0.897 × 1.75 / (0.92 − 0.12) = 1.56975 / 0.8 = 1.9621875 m per frame height", () => {
    const s = scaleFrom({ kind: "stature", statureM: 1.75, eyeY: 0.12, ankleY: 0.92 });
    expect(s.ok).toBe(true);
    if (!s.ok) return;
    expect(s.metersPerUnit).toBeCloseTo(1.9621875, 9);
    expect(s.quantity.tag).toBe("ESTIMATE");
    expect(s.quantity.note).toContain(SCALE_SENTENCE);
    expect(s.quantity.note).toMatch(/stature/i);
  });

  it("a method that cannot give a scale says why and gives no number", () => {
    const tooShort = scaleFrom({ kind: "known-length", lengthM: 0.3, yA: 0.5, yB: 0.52 });
    expect(tooShort.ok).toBe(false);
    if (!tooShort.ok) expect(tooShort.reason.length).toBeGreaterThan(10);
    const inverted = scaleFrom({ kind: "stature", statureM: 1.75, eyeY: 0.9, ankleY: 0.2 });
    expect(inverted.ok).toBe(false);
    const nonsense = scaleFrom({ kind: "known-length", lengthM: -1, yA: 0.1, yB: 0.9 });
    expect(nonsense.ok).toBe(false);
    const nan = scaleFrom({ kind: "stature", statureM: Number.NaN, eyeY: 0.1, ankleY: 0.9 });
    expect(nan.ok).toBe(false);
  });

  it("a height typed in centimetres (175) gives no scale, and the reason names metres", () => {
    const cm = scaleFrom({ kind: "stature", statureM: 175, eyeY: 0.12, ankleY: 0.92 }); // would read about 196 m per frame height
    expect(cm.ok).toBe(false);
    if (cm.ok) return;
    expect(cm.reason).toMatch(/metres/);
    expect(cm.reason).toContain(`${CAPTURE_LIMITS.statureM.min} to ${CAPTURE_LIMITS.statureM.max} m`);
  });

  it("a known length typed in centimetres (30) gives no scale, and the reason names metres", () => {
    const cm = scaleFrom({ kind: "known-length", lengthM: 30, yA: 0.4, yB: 0.6 }); // would read 150 m per frame height
    expect(cm.ok).toBe(false);
    if (cm.ok) return;
    expect(cm.reason).toMatch(/metres/);
    expect(cm.reason).toContain(`${CAPTURE_LIMITS.knownLengthM.min} to ${CAPTURE_LIMITS.knownLengthM.max} m`);
  });

  it("the scale inputs are accepted at their limits and refused just outside them", () => {
    const length = (lengthM: number) => scaleFrom({ kind: "known-length", lengthM, yA: 0.4, yB: 0.7 }).ok;
    const stature = (statureM: number) => scaleFrom({ kind: "stature", statureM, eyeY: 0.12, ankleY: 0.92 }).ok;
    const { knownLengthM, statureM } = CAPTURE_LIMITS;
    expect([length(knownLengthM.min), length(knownLengthM.max)]).toEqual([true, true]);
    expect([length(knownLengthM.min - 0.001), length(knownLengthM.max + 0.001)]).toEqual([false, false]);
    expect([stature(statureM.min), stature(statureM.max)]).toEqual([true, true]);
    expect([stature(statureM.min - 0.001), stature(statureM.max + 0.001)]).toEqual([false, false]);
  });

  it("the limits are plausible for a person and a hand-held object, in metres", () => {
    expect(CAPTURE_LIMITS.statureM).toMatchObject({ min: 1, max: 2.5 });
    expect(CAPTURE_LIMITS.knownLengthM).toMatchObject({ min: 0.05, max: 3 });
  });
});

describe("inputs", () => {
  it("accepts a mass, a gravity and a device force, and says what is wrong otherwise", () => {
    expect(captureInputProblem(earth)).toBeNull();
    expect(captureInputProblem({ ...earth, massKg: 0 })).toMatch(/mass/i);
    expect(captureInputProblem({ ...earth, massKg: Number.NaN })).toMatch(/mass/i);
    expect(captureInputProblem({ ...earth, deviceForceN: -5 })).toMatch(/force/i);
    expect(captureInputProblem({ ...earth, deviceForceN: Number.NaN })).toMatch(/not a number/i);
    expect(captureInputProblem({ ...earth, gEnvMs2: -1 })).toMatch(/gravity/i);
  });

  it("the mass and the device force are accepted at their limits and refused just outside them, with the unit in the sentence", () => {
    const { massKg, deviceForceN } = CAPTURE_LIMITS;
    expect(captureInputProblem({ ...earth, massKg: massKg.min })).toBeNull();
    expect(captureInputProblem({ ...earth, massKg: massKg.max })).toBeNull();
    expect(captureInputProblem({ ...earth, massKg: massKg.min - 0.01 })).toMatch(/kilograms/);
    expect(captureInputProblem({ ...earth, massKg: massKg.max + 0.1 })).toMatch(/kilograms/);
    expect(captureInputProblem({ ...earth, massKg: 5000 })).toContain(`${massKg.min} to ${massKg.max} kg`);
    expect(captureInputProblem({ ...earth, deviceForceN: deviceForceN.min })).toBeNull();
    expect(captureInputProblem({ ...earth, deviceForceN: deviceForceN.max })).toBeNull();
    expect(captureInputProblem({ ...earth, deviceForceN: deviceForceN.max + 1 })).toMatch(/newtons/);
    expect(captureInputProblem({ ...earth, deviceForceN: 1e9 })).toContain(`${deviceForceN.min} to ${deviceForceN.max} N`);
    expect(captureInputProblem({ ...earth, deviceForceN: Number.POSITIVE_INFINITY })).toMatch(/newtons/);
  });

  it("the device force has the limit of the squat device in the other view, and the mass is a liftable one", () => {
    const squatDevice = PARAM_FIELDS.squats.find((f) => f.key === "deviceForceN");
    expect(squatDevice).toMatchObject({ min: CAPTURE_LIMITS.deviceForceN.min, max: CAPTURE_LIMITS.deviceForceN.max });
    expect(CAPTURE_LIMITS.massKg).toMatchObject({ min: 0.1, max: 500 });
  });
});

describe("a recording that is analysed", () => {
  const outcome = analyseRecording(syntheticSession(lift), earth, label);

  it("becomes a camera SessionResult: ESTIMATE energy and peak load (unvalidated), and no bout for the load stimulus", () => {
    expect(outcome.kind).toBe("analysed");
    if (outcome.kind !== "analysed") return;
    const s = outcome.session;
    expect(s.id).toBe("camera-1");
    expect(s.title).toBe("Camera set");
    expect(s.energy.tag).toBe("ESTIMATE"); // F2: was MEASURED
    expect(s.peakLoad.tag).toBe("ESTIMATE"); // F2: was MEASURED
    expect(s.energy.value as number).toBeGreaterThan(147.15 * 0.97);
    expect(s.energy.value as number).toBeLessThan(147.15 * 1.03);
    expect(s.peakLoad.value as number).toBeGreaterThan(126.97 * 0.97);
    expect(s.peakLoad.value as number).toBeLessThan(126.97 * 1.03);
    expect(s.bout).toBeNull();
    expect(s.boutInputs).toEqual([]);
    expect(outcome.reps).toHaveLength(3);
  });

  it("carries the inputs and the caveats in its details, each with a tag and a note", () => {
    if (outcome.kind !== "analysed") throw new Error("expected analysed");
    const labels = outcome.session.details.map((d) => d.label);
    expect(labels).toEqual(expect.arrayContaining(["Mass of the weight", "Gravity", "Scale", "Reps detected"]));
    const scale = outcome.session.details.find((d) => d.label === "Scale");
    expect(scale?.tag).toBe("ESTIMATE");
    expect(scale?.note).toContain(SCALE_SENTENCE);
    const reps = outcome.session.details.find((d) => d.label === "Reps detected");
    expect(reps?.note).toContain(CONFIDENCE_SENTENCE);
    for (const d of outcome.session.details) expect(d.note.trim().length).toBeGreaterThan(0);
  });

  it("the scale note says once that scale is the largest error, whether or not the caller's note already did", () => {
    const withNote = analyseRecording(syntheticSession(lift), { ...earth, scaleNote: `From a known length. ${SCALE_SENTENCE}` }, label);
    const without = analyseRecording(syntheticSession(lift), { ...earth, scaleNote: "From a known length." }, label);
    for (const o of [withNote, without]) {
      if (o.kind !== "analysed") throw new Error("expected analysed");
      const note = o.session.details.find((d) => d.label === "Scale")?.note ?? "";
      expect(note.split(SCALE_SENTENCE)).toHaveLength(2);
    }
  });

  it("reports confidence with the sentence that it grades conditions, not accuracy", () => {
    if (outcome.kind !== "analysed") throw new Error("expected analysed");
    expect(["LOW", "MEDIUM"]).toContain(outcome.confidence); // capped at MEDIUM until validated on real video
    expect(outcome.confidenceSentence).toContain(CONFIDENCE_SENTENCE);
    expect(CONFIDENCE_SENTENCE).toMatch(/recording conditions, not accuracy/);
    expect(CONFIDENCE_SENTENCE).toMatch(/capped until validated on real video/);
  });

  it("ordinary reps carry no flags", () => {
    if (outcome.kind !== "analysed") throw new Error("expected analysed");
    for (const row of outcome.reps) expect(row.notes).toEqual([]);
  });

  it("in orbit with a 1000 N device force the work is the device force times the height: 1000 × 0.5 × 3 = 1500 J", () => {
    const iss = analyseRecording(syntheticSession(lift), { ...earth, gEnvMs2: 0, deviceForceN: 1000 }, label);
    if (iss.kind !== "analysed") throw new Error("expected analysed");
    expect(iss.session.energy.value as number).toBeGreaterThan(1500 * 0.97);
    expect(iss.session.energy.value as number).toBeLessThan(1500 * 1.03);
  });
});

describe("a fast lift", () => {
  // A 0.4 s lift of 0.5 m: liftDurationS reads about 0.85 × 0.4 = 0.34 s, under the 0.65 s limit.
  it("carries the note that it is too fast for the filter and that work and peak force are under-read", () => {
    const fast = analyseRecording(syntheticSession({ ...lift, upS: 0.4, downS: 0.4 }), earth, label);
    if (fast.kind !== "analysed") throw new Error("expected analysed");
    expect(fast.reps.length).toBeGreaterThan(0);
    for (const row of fast.reps) {
      expect(row.rep.filterLimited).toBe(true);
      expect(row.notes.join(" ")).toMatch(/too fast for the filter/i);
      expect(row.notes.join(" ")).toMatch(/under-read/i);
    }
    expect(fast.session.details.some((d) => /too fast/i.test(d.label))).toBe(true);
  });
});

describe("repNotes", () => {
  const rep: RepResult = {
    startS: 1,
    durationS: 2,
    liftDurationS: 0.85,
    filterLimited: false,
    rangeOfMotionM: 0.5,
    pathLengthM: 1,
    trimmedRangeFraction: 1,
    positiveWorkJ: 49,
    negativeWorkJ: -49,
    peakForceN: 127,
    impulseNs: 0,
  };

  it("no flags for a rep that is neither fast nor trimmed", () => {
    expect(repNotes(rep)).toEqual([]);
    expect(repNotes({ ...rep, trimmedRangeFraction: 0.9 })).toEqual([]);
  });

  it("a rep measured over half the detected movement says so, as a percentage", () => {
    const notes = repNotes({ ...rep, trimmedRangeFraction: 0.5 });
    expect(notes).toHaveLength(1);
    expect(notes[0]).toBe("Measured over 50 % of the detected movement.");
  });

  it("the threshold is under 0.9 and the percentage is rounded", () => {
    expect(repNotes({ ...rep, trimmedRangeFraction: 0.899 })[0]).toBe("Measured over 90 % of the detected movement.");
    expect(repNotes({ ...rep, trimmedRangeFraction: 0.451 })[0]).toBe("Measured over 45 % of the detected movement.");
  });

  it("a filter-limited rep and a trimmed rep carry both notes", () => {
    const notes = repNotes({ ...rep, filterLimited: true, trimmedRangeFraction: 0.45 });
    expect(notes).toHaveLength(2);
    expect(notes[0]).toBe("Too fast for the filter; work and peak force are under-read.");
  });
});

describe("a recording that is refused", () => {
  it("gives a sentence per reason and no numbers", () => {
    const lost: PoseFrame[] = syntheticSession(lift).map((f) => ({ ...f, visibility: 0 }));
    const outcome = analyseRecording(lost, earth, label);
    expect(outcome.kind).toBe("refused");
    if (outcome.kind !== "refused") return;
    expect(outcome.reasons.length).toBeGreaterThan(0);
    for (const r of outcome.reasons) {
      expect(r.sentence.trim().length).toBeGreaterThan(20);
      expect(r.sentence).not.toMatch(/[A-Z]+_[A-Z]+/); // no raw reason code in the sentence
    }
    expect(outcome.reasons.map((r) => r.code)).toContain("LANDMARK_LOST");
    // M13: assert the exact shape, not a case-sensitive regex over the JSON: a refusal has these keys and no others
    expect(Object.keys(outcome).sort()).toEqual(["kind", "reasons"]);
    for (const r of outcome.reasons) expect(Object.keys(r).sort()).toEqual(["code", "sentence"]);
  });

  it("no scale is its own reason", () => {
    const outcome = analyseRecording(syntheticSession(lift), { ...earth, metersPerUnit: null }, label);
    expect(outcome.kind).toBe("refused");
    if (outcome.kind !== "refused") return;
    expect(outcome.reasons.map((r) => r.code)).toContain("NO_SCALE");
  });

  it("a stream that is too slow is refused for its frame rate", () => {
    const slow = syntheticSession({ ...lift, rateHz: 10 });
    const outcome = analyseRecording(slow, earth, label);
    expect(outcome.kind).toBe("refused");
    if (outcome.kind !== "refused") return;
    expect(outcome.reasons.map((r) => r.code)).toContain("LOW_FRAME_RATE");
  });

  it("a recording with no movement has no rep: refused by the capture package, with its own sentence", () => {
    const still = syntheticSession({ ...lift, reps: 0, restS: 5 });
    const outcome = analyseRecording(still, earth, label);
    expect(outcome.kind).toBe("refused");
    if (outcome.kind !== "refused") return;
    expect(outcome.reasons.map((r) => r.code)).toEqual(["NO_REPS"]);
    expect(outcome.reasons[0]?.sentence).toMatch(/10 cm/);
  });

  it("every reason has a sentence", () => {
    const sentences = refusalSentences(["NO_SCALE", "LOW_FRAME_RATE", "LANDMARK_LOST", "GAP_TOO_LONG", "TOO_SHORT", "NO_REPS"]);
    expect(sentences).toHaveLength(6);
    expect(new Set(sentences).size).toBe(6);
    for (const s of sentences) expect(s.trim().length).toBeGreaterThan(20);
  });
});

describe("when a scale can be taken", () => {
  const ok = { frozen: true, endA: true, endB: true, lengthM: 0.3 };

  it("known length needs a frozen frame, both ends set after the freeze, and a positive length", () => {
    expect(knownLengthReady(ok)).toBe(true);
    expect(knownLengthReady({ ...ok, frozen: false })).toBe(false);
    expect(knownLengthReady({ ...ok, endA: false })).toBe(false);
    expect(knownLengthReady({ ...ok, endB: false })).toBe(false);
    expect(knownLengthReady({ ...ok, lengthM: 0 })).toBe(false);
    expect(knownLengthReady({ ...ok, lengthM: Number.NaN })).toBe(false);
  });

  it("known length: a typed length alone, with nothing frozen and no taps, is not a scale", () => {
    expect(knownLengthReady({ frozen: false, endA: false, endB: false, lengthM: 0.3 })).toBe(false);
  });

  it("stature needs a frozen frame, a pose read from that frame, and a positive height", () => {
    expect(statureReady({ frozen: true, poseRead: true, statureM: 1.75 })).toBe(true);
    expect(statureReady({ frozen: false, poseRead: true, statureM: 1.75 })).toBe(false);
    expect(statureReady({ frozen: true, poseRead: false, statureM: 1.75 })).toBe(false);
    expect(statureReady({ frozen: true, poseRead: true, statureM: -1 })).toBe(false);
  });
});

describe("cancelling a pending open", () => {
  it("only the latest open is current; an earlier one that resolves late must release what it acquired", () => {
    const gate = createGate();
    const first = gate.next();
    expect(gate.isCurrent(first)).toBe(true);
    const second = gate.next(); // a second quick click
    expect(gate.isCurrent(first)).toBe(false);
    expect(gate.isCurrent(second)).toBe(true);
  });

  it("invalidate (leaving the tab) supersedes the pending open without starting another", () => {
    const gate = createGate();
    const pending = gate.next();
    gate.invalidate();
    expect(gate.isCurrent(pending)).toBe(false);
    expect(gate.isCurrent(gate.next())).toBe(true);
  });

  it("a token that was never issued is not current", () => {
    expect(createGate().isCurrent(1)).toBe(false);
  });
});

describe("timestamps", () => {
  it("a browser that gives frame times may record; one that does not is refused with a sentence", () => {
    expect(timingProblem(true)).toBeNull();
    const sentence = timingProblem(false);
    expect(sentence).toMatch(/capture timestamps/i);
    expect(sentence?.length).toBeGreaterThan(30);
  });
});

describe("the device force field (M5)", () => {
  it("empty means none, a number is itself, and unparseable input is NaN, never silently 0", () => {
    expect(parseDeviceForce("", false)).toBe(0);
    expect(parseDeviceForce("  ", false)).toBe(0);
    expect(parseDeviceForce("1000", false)).toBe(1000);
    expect(parseDeviceForce("12.5", false)).toBe(12.5);
    expect(parseDeviceForce("", true)).toBeNaN(); // the browser's badInput: an empty value that is not empty
    expect(parseDeviceForce("1e", false)).toBeNaN();
  });
});

describe("the camera set's peak load is the largest peak force (M13)", () => {
  // Two reps of 0.5 m: one lifted in 1.0 s, one in 1.6 s. Hand: a_peak = (10 / √3) h / T², so F = 10 (9.81 + a_peak):
  //   T = 1.0 s: a = 5.7735 × 0.5 / 1.00 = 2.887 m/s², F = 126.97 N
  //   T = 1.6 s: a = 5.7735 × 0.5 / 2.56 = 1.128 m/s², F = 109.38 N
  const fast: [number, number][] = [[1, 0], [1, 0.5], [1, 0], [1, 0]];
  const slow: [number, number][] = [[1.6, 0.5], [1.6, 0], [1, 0]];
  const run = (legs: [number, number][]) => analyseRecording(legSession({ legs, metersPerUnit: 2.5 }), earth, label);

  it.each([
    ["fast first", [...fast, ...slow]],
    ["fast last", [[1, 0], ...slow, [1, 0], ...fast.slice(1)] as [number, number][]],
  ])("%s: peak load is the maximum over the reps, and the reps differ", (_name, legs) => {
    const o = run(legs as [number, number][]);
    if (o.kind !== "analysed") throw new Error("expected analysed");
    const peaks = o.reps.map((r) => r.rep.peakForceN);
    expect(o.reps).toHaveLength(2);
    expect(Math.min(...peaks)).toBeLessThan(Math.max(...peaks) - 10); // 127 against 109: a first-or-last rule would be wrong
    expect(o.session.peakLoad.value).toBe(Math.max(...peaks));
    expect(o.session.peakLoad.value as number).toBeGreaterThan(120);
    expect(o.session.energy.value).toBeCloseTo(o.reps.reduce((sum, r) => sum + r.rep.positiveWorkJ, 0), 9);
  });
});
