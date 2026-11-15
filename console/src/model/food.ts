import { COPY } from "../copy";
import type { CrewId, FoodCatalog, FoodItem, IntakeInd, MealRequest, NutrientTotal } from "../contract";
import { INTAKE_INDS } from "../contract";

export const NUTRIENT_LABEL: Record<IntakeInd, string> = {
  intake_kcal: "Food energy",
  intake_protein_g: "Protein",
  intake_carb_g: "Carbohydrate",
  intake_fat_g: "Fat",
  intake_water_ml: "Drinking fluid",
  intake_sodium_mg: "Sodium",
  intake_potassium_mg: "Potassium",
  intake_calcium_mg: "Calcium",
  intake_iron_mg: "Iron",
  intake_vitd_ug: "Vitamin D",
};

// The only place that writes a food-energy unit for display.
const UNIT: Record<IntakeInd, { unit: string; decimals: number }> = {
  intake_kcal: { unit: "kcal", decimals: 0 },
  intake_protein_g: { unit: "g", decimals: 1 },
  intake_carb_g: { unit: "g", decimals: 1 },
  intake_fat_g: { unit: "g", decimals: 1 },
  intake_water_ml: { unit: "mL", decimals: 0 },
  intake_sodium_mg: { unit: "mg", decimals: 0 },
  intake_potassium_mg: { unit: "mg", decimals: 0 },
  intake_calcium_mg: { unit: "mg", decimals: 0 },
  intake_iron_mg: { unit: "mg", decimals: 1 },
  intake_vitd_ug: { unit: "µg", decimals: 1 },
};

/** A value that was not reported is "—", never 0. */
export function formatNutrient(ind: IntakeInd, val: number | null): string {
  if (val === null || val === undefined || Number.isNaN(val)) return COPY["status.none"];
  const u = UNIT[ind];
  return `${val.toFixed(u.decimals)} ${u.unit}`;
}

export function reportedBy(t: Pick<NutrientTotal, "meals_reporting" | "meals_total">): string {
  return COPY["food.reportedBy"].replace("{r}", String(t.meals_reporting)).replace("{t}", String(t.meals_total));
}

export type Selection = { food_id: string; servings: number }[];

export function validSelection(sel: Selection): boolean {
  return sel.length > 0 && sel.length <= 20 && sel.every((s) => s.servings > 0 && s.servings <= 20);
}

export function buildMealRequest(crew: CrewId | null, sel: Selection): MealRequest {
  return { crew, items: sel.map((s) => ({ food_id: s.food_id, servings: s.servings })) };
}

const KEY: Record<IntakeInd, keyof FoodItem["per100g"] | "fluid"> = {
  intake_kcal: "kcal",
  intake_protein_g: "protein_g",
  intake_carb_g: "carb_g",
  intake_fat_g: "fat_g",
  intake_water_ml: "fluid",
  intake_sodium_mg: "sodium_mg",
  intake_potassium_mg: "potassium_mg",
  intake_calcium_mg: "calcium_mg",
  intake_iron_mg: "iron_mg",
  intake_vitd_ug: "vitd_ug",
};

/** Draft-meal sums. A nutrient that any item does not report stays null (not 0). */
export function mealPreview(catalog: FoodCatalog, sel: Selection): Record<IntakeInd, number | null> {
  const out = {} as Record<IntakeInd, number | null>;
  for (const ind of INTAKE_INDS) {
    let sum: number | null = 0;
    for (const s of sel) {
      const item = catalog.items.find((i) => i.id === s.food_id);
      if (!item || sum === null) {
        sum = null;
        break;
      }
      const k = KEY[ind];
      const v = k === "fluid" ? item.fluid_ml_per_serving * s.servings : item.per100g[k];
      sum = v === null ? null : sum + (k === "fluid" ? v : (v * item.serving_g * s.servings) / 100);
    }
    out[ind] = sel.length === 0 ? null : sum;
  }
  return out;
}

/** Food energy logged in a day window, formatted with its unit (the panel shows it without naming the unit itself). */
export function foodEnergyLogged(day: { totals: Partial<Record<IntakeInd, Pick<NutrientTotal, "val">>> }): string {
  return formatNutrient("intake_kcal", day.totals.intake_kcal?.val ?? null);
}
