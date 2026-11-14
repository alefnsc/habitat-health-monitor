import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { GuidanceItem } from "../src/model/guidance";
import { ruleBrand, ruleCalories, ruleDiagnosis, ruleEnergyBalance, ruleNonEnglish, ruleTreatmentDose } from "./honesty";

const items: GuidanceItem[] = JSON.parse(readFileSync(join(__dirname, "..", "..", "data", "guidance.json"), "utf8"));
const byId = new Map(items.map((i) => [i.id, i]));

describe("data/guidance.json", () => {
  test("test_split_rows_expanded", () => {
    expect(byId.get("bp_sys_high.watch")?.do_now).toBeTruthy();
    expect(byId.get("bp_dia_high.watch")?.do_now).toBe(byId.get("bp_sys_high.watch")?.do_now);
    expect(byId.has("cabin_health_box_temp.act")).toBe(true);
    expect(byId.has("cabin_health_box_rh.act")).toBe(true);
    for (const i of items) {
      if (i.status === "info" || i.id.startsWith("default.")) continue;
      expect(`${i.rule_id}.${i.status}`, i.id).toBe(i.id);
    }
  });

  test("test_why_file", () => {
    for (const i of items) {
      if (i.why === undefined) continue;
      expect(i.why.length, i.id).toBeLessThanOrEqual(160);
      for (const rule of [ruleCalories, ruleEnergyBalance, ruleDiagnosis, ruleTreatmentDose, ruleBrand, ruleNonEnglish]) {
        expect(rule(i.why), i.id).toBe(false);
      }
    }
  });
});
