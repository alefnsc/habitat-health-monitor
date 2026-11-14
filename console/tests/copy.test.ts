import { describe, expect, test } from "vitest";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { COPY, DISCLAIMER } from "../src/copy";
import {
  ruleBrand, ruleCalories, ruleCameraWording, ruleDiagnosis, ruleEnergyBalance, ruleMealPlan, ruleNonEnglish,
  ruleTreatmentDose, stringLiterals,
} from "./honesty";

const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");

function tsFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? tsFiles(join(dir, e.name)) : e.name.endsWith(".ts") ? [join(dir, e.name)] : [],
  );
}
const rel = (p: string) => p.slice(ROOT.length + 1).replace(/\\/g, "/");

interface Walked { text: string; where: string; foodExempt: boolean; camera: boolean }

function walkAll(): Walked[] {
  const out: Walked[] = [];
  for (const [k, v] of Object.entries(COPY)) {
    out.push({ text: v, where: `COPY.${k}`, foodExempt: k.startsWith("food."), camera: false });
  }
  out.push({ text: DISCLAIMER, where: "DISCLAIMER", foodExempt: false, camera: false });
  const viewFiles = tsFiles(join(ROOT, "src", "views"));
  for (const f of viewFiles) {
    for (const s of stringLiterals(readFileSync(f, "utf8"))) {
      out.push({ text: s, where: rel(f), foodExempt: rel(f) === "src/views/food.ts", camera: false });
    }
  }
  for (const f of tsFiles(join(REPO, "camera", "src"))) {
    for (const s of stringLiterals(readFileSync(f, "utf8"))) {
      out.push({ text: s, where: `camera/${f.split("/camera/")[1]}`, foodExempt: false, camera: true });
    }
  }
  const guidance = join(REPO, "data", "guidance.json");
  if (existsSync(guidance)) {
    const g = JSON.parse(readFileSync(guidance, "utf8"));
    const entries: unknown[] = Array.isArray(g) ? g : Object.values(g);
    for (const e of entries as Record<string, string>[]) {
      for (const k of ["do_now", "tell", "why"]) {
        if (typeof e?.[k] === "string") out.push({ text: e[k], where: `guidance.${k}`, foodExempt: false, camera: false });
      }
    }
  }
  return out;
}

const ALL = walkAll();
const bad = (rule: (s: string) => boolean, items: Walked[] = ALL) =>
  items.filter((w) => rule(w.text)).map((w) => `${w.where}: ${w.text}`);

describe("honesty lint", () => {
  test("self-check: rules catch the fixed samples", () => {
    for (const s of ["300 kcal", "Calories burned", "calorie"]) expect(ruleCalories(s)).toBe(true);
    for (const s of ["Calibrate the scale", "Work is mechanical work in joules, not food energy."]) {
      expect(ruleCalories(s)).toBe(false);
    }
    expect(ruleCalories("Food energy logged")).toBe(false);
  });

  test("test_no_calories", () => {
    const nonFood = ALL.filter((w) => !w.foodExempt);
    expect(bad(ruleCalories, nonFood)).toEqual([]);
    expect(COPY["food.energyTitle"]).toBe("Food energy logged");
  });

  test("test_no_energy_balance", () => {
    for (const s of ["net calories", "calories burned", "burn", "deficit", "surplus", "energy balance", "balance",
      "lose weight", "diet"]) expect(ruleEnergyBalance(s)).toBe(true);
    for (const s of ["Training work", "not converted or compared", "Audit trail"]) expect(ruleEnergyBalance(s)).toBe(false);
    expect(bad(ruleEnergyBalance)).toEqual([]);
  });

  test("test_no_conversion", () => {
    const files = tsFiles(join(ROOT, "src"));
    for (const f of files) {
      const t = readFileSync(f, "utf8");
      expect(/4\.184|4\.18\b|4184/.test(t), rel(f)).toBe(false);
      // kcal and kJ together in one file: only the id/unit tables may mention kcal, and none mention kJ.
      expect(t.includes("kcal") && t.includes("kJ"), rel(f)).toBe(false);
    }
    for (const w of ALL) expect(w.text.includes("kcal") && w.text.includes("kJ"), w.where).toBe(false);
  });

  test("test_unit_files", () => {
    // kJ only in model/exercise.ts. kcal only in the food files and the two indicator tables
    // (contract.ts ids, payload.ts UNITS), which hold ids and units, not display text.
    const kcalOk = new Set(["src/model/food.ts", "src/views/food.ts", "src/contract.ts", "src/payload.ts"]);
    for (const f of tsFiles(join(ROOT, "src"))) {
      const t = readFileSync(f, "utf8");
      if (t.includes("kJ")) expect(rel(f)).toBe("src/model/exercise.ts");
      if (t.includes("kcal")) expect(kcalOk.has(rel(f)), rel(f)).toBe(true);
    }
  });

  test("test_no_meal_plan", () => {
    for (const s of ["Your meal plan", "You should eat more iron", "Recommended menu"]) expect(ruleMealPlan(s)).toBe(true);
    expect(ruleMealPlan("Meal logged")).toBe(false);
    expect(bad(ruleMealPlan)).toEqual([]);
  });

  test("test_no_diagnosis", () => {
    for (const s of ["diagnosis", "Diagnosed"]) expect(ruleDiagnosis(s)).toBe(true);
    const others = ALL.filter((w) => w.where !== "DISCLAIMER" && w.where !== "COPY.app.disclaimer");
    expect(bad(ruleDiagnosis, others)).toEqual([]);
  });

  test("test_no_treatment_dose", () => {
    for (const s of ["take 5 mg", "2 units", "10 ml", "250 mcg"]) expect(ruleTreatmentDose(s)).toBe(true);
    for (const s of ["95 mg/dL", "140 mg/dL or above", "600 mSv", "41.7 mGy", "3.0 mmHg"]) {
      expect(ruleTreatmentDose(s)).toBe(false);
    }
    expect(bad(ruleTreatmentDose)).toEqual([]);
  });

  test("test_no_brand_names", () => {
    for (const s of ["Polar", "garmin", "Apple Watch", "Oura", "Withings", "Google", "Lightstreamer", "Vocaid", "Omron"]) {
      expect(ruleBrand(s)).toBe(true);
    }
    expect(bad(ruleBrand)).toEqual([]);
  });

  test("test_english_only", () => {
    expect(ruleNonEnglish("coração")).toBe(true);
    expect(bad(ruleNonEnglish)).toEqual([]);
  });

  test("test_camera_wording", () => {
    for (const s of ["measured", "Validated", "accurate"]) expect(ruleCameraWording(s)).toBe(true);
    expect(bad(ruleCameraWording, ALL.filter((w) => w.camera))).toEqual([]);
  });

  test("test_disclaimer_exact", () => {
    expect(DISCLAIMER).toBe("This is not a diagnosis.");
  });
});
