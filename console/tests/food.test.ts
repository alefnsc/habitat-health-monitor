import { describe, expect, test } from "vitest";
import type { FoodCatalog, FoodItem } from "../src/contract";
import { buildMealRequest, formatNutrient, mealLine, mealPreview, reportedBy, validSelection } from "../src/model/food";

const item = (id: string, g: number, fluid: number, per: (number | null)[]): FoodItem => ({
  id, name: id, category: "test", fdc_id: 1, fdc_dataset: "sr_legacy", fdc_description: "t", serving_g: g,
  serving_label: `${g} g`, serving_source: "team-chosen", fluid_ml_per_serving: fluid, fluid_basis: "t",
  per100g: { kcal: per[0], protein_g: per[1], carb_g: per[2], fat_g: per[3], sodium_mg: per[4], potassium_mg: per[5],
    calcium_mg: per[6], iron_mg: per[7], vitd_ug: per[8] } as FoodItem["per100g"],
  kcal_basis: "measured_1008", note: "test data",
});
const cat = {
  items: [
    item("bar", 40, 0, [400, 10, 60, 12, 200, 300, 50, 2, null]),
    item("drink", 250, 250, [40, 0, 10, 0, 20, 100, 10, 0.1, 0]),
  ],
} as unknown as FoodCatalog;

describe("food model", () => {
  test("formatNutrient shows not reported as a dash, never 0", () => {
    expect(formatNutrient("intake_kcal", null)).toBe("—");
    expect(formatNutrient("intake_kcal", 420.4)).toBe("420 kcal");
    expect(formatNutrient("intake_vitd_ug", 0)).toBe("0.0 µg");
    expect(formatNutrient("intake_water_ml", 250)).toBe("250 mL");
  });
  test("mealPreview matches the hub rules (null blocks the nutrient)", () => {
    const p = mealPreview(cat, [{ food_id: "bar", servings: 2 }, { food_id: "drink", servings: 1 }]);
    expect(p.intake_kcal).toBeCloseTo(420);
    expect(p.intake_water_ml).toBe(250);
    expect(p.intake_vitd_ug).toBeNull();
    expect(mealPreview(cat, [{ food_id: "drink", servings: 1 }]).intake_vitd_ug).toBe(0);
    expect(mealPreview(cat, []).intake_kcal).toBeNull();
  });
  test("buildMealRequest and validSelection", () => {
    expect(buildMealRequest("crew-a", [{ food_id: "bar", servings: 2 }])).toEqual({
      crew: "crew-a", items: [{ food_id: "bar", servings: 2 }],
    });
    expect(validSelection([])).toBe(false);
    expect(validSelection([{ food_id: "bar", servings: 0 }])).toBe(false);
    expect(validSelection([{ food_id: "bar", servings: 20 }])).toBe(true);
  });
  test("mealLine names each food from the catalogue and keeps the id only when the name is unknown", () => {
    const meal = { eaten_at: "2026-11-15T21:40:00Z", items: [{ food_id: "bar", servings: 2 }, { food_id: "gone", servings: 0.5 }] };
    expect(mealLine(cat, meal)).toBe("21:40 UTC: bar x 2, gone x 0.5");
    expect(mealLine(null, meal)).toBe("21:40 UTC: bar x 2, gone x 0.5");
    const named = { items: [{ ...cat.items[0], name: "Cereal bar" }] } as unknown as FoodCatalog;
    expect(mealLine(named, meal)).toBe("21:40 UTC: Cereal bar x 2, gone x 0.5");
  });
  test("reportedBy wording", () => {
    expect(reportedBy({ meals_reporting: 3, meals_total: 4 })).toBe("reported by 3 of 4 meals");
  });
});
