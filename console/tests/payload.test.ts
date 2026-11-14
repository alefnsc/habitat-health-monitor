import { describe, expect, test } from "vitest";
import { ENTRY_BOUNDS, UNITS, buildManualReadings, createSequencer } from "../src/payload";
import { INTAKE_INDS } from "../src/contract";
import type { IssReference, LinkState, NutrientTotal } from "../src/contract";

const BOOT = 1794657600;

describe("payload", () => {
  test("test_units_match_spec", () => {
    const expected: Record<string, string> = {
      hr: "bpm", spo2: "%", body_temp: "C", bp_sys: "mmHg", glucose: "mg/dL", sleep_h: "h", mood: "1-5",
      symptom: "code", cabin_co2: "ppm", cabin_ppco2: "mmHg", cabin_lux: "lx", space_weather: "level",
      rad_dose_cum: "mSv", intake_kcal: "kcal", intake_protein_g: "g", intake_carb_g: "g", intake_fat_g: "g",
      intake_water_ml: "mL", intake_sodium_mg: "mg", intake_potassium_mg: "mg", intake_calcium_mg: "mg",
      intake_iron_mg: "mg", intake_vitd_ug: "ug", body_mass: "kg",
    };
    for (const [k, v] of Object.entries(expected)) expect(UNITS[k as keyof typeof UNITS]).toBe(v);
  });

  test("test_intake_inds", () => {
    expect([...INTAKE_INDS]).toEqual([
      "intake_kcal", "intake_protein_g", "intake_carb_g", "intake_fat_g", "intake_water_ml",
      "intake_sodium_mg", "intake_potassium_mg", "intake_calcium_mg", "intake_iron_mg", "intake_vitd_ug",
    ]);
    for (const i of INTAKE_INDS) expect(i in ENTRY_BOUNDS).toBe(false);
  });

  test("test_manual_body_temp", () => {
    const r = buildManualReadings({ ind: "body_temp", val: 36.8 }, "crew-a", "certified", createSequencer(BOOT));
    expect(r).toEqual({
      ok: true,
      messages: [{
        v: 1, node: "manual", boot: BOOT, seq: 1, age_ms: 0, ind: "body_temp", val: 36.8, unit: "C",
        src: "certified", dev: "manual", q: ["ok"], crew: "crew-a",
      }],
    });
  });

  test("test_manual_body_mass", () => {
    const r = buildManualReadings({ ind: "body_mass", val: 70 }, "crew-a", "self", createSequencer(BOOT));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.messages).toHaveLength(1);
    expect(r.messages[0]).toMatchObject({
      node: "manual", ind: "body_mass", val: 70, unit: "kg", src: "self", dev: "manual", q: ["ok"],
      crew: "crew-a", seq: 1,
    });
    const c = buildManualReadings({ ind: "body_mass", val: 70 }, "crew-a", "certified", createSequencer(BOOT));
    expect(c.ok && c.messages[0].src).toBe("certified");
  });

  test("test_body_mass_bounds", () => {
    const err = "Body mass must be 20 to 300 kg.";
    for (const val of [19.9, 19, 300.1]) {
      expect(buildManualReadings({ ind: "body_mass", val }, "crew-a", "self", createSequencer(BOOT))).toEqual({
        ok: false, error: err,
      });
    }
    for (const val of [20, 300]) {
      expect(buildManualReadings({ ind: "body_mass", val }, "crew-a", "self", createSequencer(BOOT)).ok).toBe(true);
    }
  });

  test("test_bp_pair", () => {
    const r = buildManualReadings({ ind: "bp", sys: 118, dia: 76 }, "crew-a", "certified", createSequencer(BOOT));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.messages.map((m) => [m.ind, m.val, m.seq, m.unit, m.boot])).toEqual([
      ["bp_sys", 118, 1, "mmHg", BOOT],
      ["bp_dia", 76, 2, "mmHg", BOOT],
    ]);
  });

  test("test_bp_sys_not_above_dia", () => {
    expect(buildManualReadings({ ind: "bp", sys: 70, dia: 80 }, "crew-a", "certified", createSequencer(BOOT))).toEqual({
      ok: false, error: "Systolic must be higher than diastolic.",
    });
  });

  test("test_mood_integer", () => {
    expect(buildManualReadings({ ind: "mood", val: 3.5 }, "crew-a", "self", createSequencer(BOOT))).toEqual({
      ok: false, error: "Mood must be a whole number from 1 to 5.",
    });
    const r = buildManualReadings({ ind: "mood", val: 4 }, "crew-a", "certified", createSequencer(BOOT));
    expect(r.ok && r.messages[0]).toMatchObject({ unit: "1-5", src: "self", val: 4 });
  });

  test("test_sleep_bounds", () => {
    const bad = buildManualReadings({ ind: "sleep_h", val: 24.25 }, "crew-a", "self", createSequencer(BOOT));
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.error).toContain("0 to 24 h");
    expect(buildManualReadings({ ind: "sleep_h", val: 7.25 }, "crew-a", "self", createSequencer(BOOT)).ok).toBe(true);
  });

  test("test_symptoms_one_message_each", () => {
    const r = buildManualReadings({ ind: "symptom", codes: ["headache", "fatigue"] }, "crew-a", "self", createSequencer(BOOT));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.messages).toHaveLength(2);
    expect(r.messages.map((m) => [m.ind, m.val, m.unit, m.src, m.code])).toEqual([
      ["symptom", 1, "code", "self", "headache"],
      ["symptom", 1, "code", "self", "fatigue"],
    ]);
    expect(buildManualReadings({ ind: "symptom", codes: [] }, "crew-a", "self", createSequencer(BOOT))).toEqual({
      ok: false, error: "Pick at least one option, or None.",
    });
  });

  test("test_none_exclusive", () => {
    expect(buildManualReadings({ ind: "symptom", codes: ["none", "nausea"] }, "crew-a", "self", createSequencer(BOOT))).toEqual({
      ok: false, error: "None cannot be combined with a symptom.",
    });
  });

  test("test_entry_bounds_values", () => {
    expect(ENTRY_BOUNDS).toEqual({
      hr: { min: 20, max: 250, step: 1 },
      spo2: { min: 50, max: 100, step: 1 },
      body_temp: { min: 30.0, max: 45.0, step: 0.1 },
      bp_sys: { min: 60, max: 260, step: 1 },
      bp_dia: { min: 30, max: 160, step: 1 },
      glucose: { min: 20, max: 600, step: 1 },
      sleep_h: { min: 0, max: 24, step: 0.25 },
      mood: { min: 1, max: 5, step: 1 },
      body_mass: { min: 20, max: 300, step: 0.1 },
    });
  });

  test("test_payload_size", () => {
    const r = buildManualReadings({ ind: "symptom", codes: ["poor_sleep"] }, "crew-a", "self", createSequencer(BOOT));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(new TextEncoder().encode(JSON.stringify(r.messages[0])).length).toBeLessThanOrEqual(256);
  });

  test("test_type_shapes", () => {
    const link: LinkState = {
      state: "blackout", light_time_s: 600, time_scale: 1, queue_len: 0,
      last_blackout: { start: "2026-11-15T13:00:00.000Z", end: null },
    };
    const dose = {
      absorbed_mgy: null, absorbed_mgy_per_day: null, effective_msv: null, effective_msv_method: null,
      career_limit_msv: null, career_fraction: null, status: "unknown" as const, profile: null, mission_day: null,
    };
    const base = { snapshot_date: "2026-01-01", mission: "m", source_urls: [], label: "l", dose };
    const a: IssReference = { ...base, cabin: { temperature_c: null, rh_pct: null, co2_mmhg: null, co2_raw_unit: "mmHg" } };
    const b: IssReference = { ...base, cabin: null };
    const n: NutrientTotal = {
      val: 1, meals_reporting: 1, meals_total: 1, status: "ok", rule_id: null, source_kind: null, source_ref: null,
      escalate_to: "self", floor_judged: false,
    };
    expect([link, a, b, n]).toHaveLength(4);
  });
});
