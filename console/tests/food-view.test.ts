// @vitest-environment jsdom
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { FoodCatalog, FoodDay } from "../src/contract";
import { INTAKE_INDS } from "../src/contract";

const api = vi.hoisted(() => ({
  getFoodCatalog: vi.fn(),
  getFoodReferences: vi.fn(),
  getFoodDay: vi.fn(),
  getExerciseDay: vi.fn(),
  postFoodLog: vi.fn(),
}));
vi.mock("../src/api", async (orig) => ({ ...(await orig<typeof import("../src/api")>()), ...api }));

import { COPY } from "../src/copy";
import { setCurrentCrew } from "../src/crew";
import { renderFood } from "../src/views/food";

const catalog = {
  items: [{ id: "bar", name: "Cereal bar", serving_label: "40 g", serving_g: 40, fluid_ml_per_serving: 0, per100g: {} }],
} as unknown as FoodCatalog;

const day = (meals: FoodDay["meals"] = []): FoodDay => ({
  crew: null,
  window_start: "2026-11-14T12:00:00+00:00",
  window_end: "2026-11-15T12:00:00+00:00",
  totals: Object.fromEntries(INTAKE_INDS.map((i) => [i, {
    val: null, meals_reporting: 0, meals_total: 0, status: "unknown", rule_id: null, source_kind: null,
    source_ref: null, escalate_to: "self", floor_judged: null,
  }])) as FoodDay["totals"],
  meals,
  body_mass: null,
});

const flush = () => new Promise((r) => setTimeout(r, 0));
const button = (root: Element, text: string) =>
  [...root.querySelectorAll("button")].find((b) => b.textContent === text) as HTMLButtonElement;
const crewPick = (root: Element) => root.querySelector("#food-crew") as HTMLSelectElement;

async function mount(): Promise<HTMLElement> {
  const root = document.createElement("div");
  renderFood(root);
  await flush();
  return root;
}

async function draftOneBar(root: HTMLElement) {
  (root.querySelector("#food-item") as HTMLSelectElement).value = "bar";
  button(root, COPY["food.addItem"]).click();
}

describe("food screen: who ate the meal (S4)", () => {
  beforeEach(() => {
    setCurrentCrew(null);
    vi.clearAllMocks();
    api.getFoodCatalog.mockResolvedValue(catalog);
    api.getFoodReferences.mockResolvedValue({ items: [], notes: [] });
    api.getFoodDay.mockResolvedValue(day());
    api.getExerciseDay.mockRejectedValue(new Error("not needed"));
    api.postFoodLog.mockResolvedValue({ meal_id: 1, readings: [], not_reported: [], results: [] });
  });

  test("viewing all crew, the crew list starts on 'Pick the crew' and a meal is not logged", async () => {
    const root = await mount();
    const pick = crewPick(root);
    expect(pick).not.toBeNull();
    expect(pick.value).toBe("");
    expect(pick.options[0].textContent).toBe(COPY["crew.pick"]);
    await draftOneBar(root);
    button(root, COPY["food.logMeal"]).click();
    await flush();
    expect(api.postFoodLog).not.toHaveBeenCalled();
    expect(root.textContent).toContain(COPY["crew.needed"]);
  });

  test("once a crew is picked, the meal is logged for that crew", async () => {
    const root = await mount();
    crewPick(root).value = "crew-b";
    await draftOneBar(root);
    button(root, COPY["food.logMeal"]).click();
    await flush();
    expect(api.postFoodLog).toHaveBeenCalledWith({ crew: "crew-b", items: [{ food_id: "bar", servings: 1 }] });
  });

  test("the crew list starts on, and follows, the crew being viewed", async () => {
    setCurrentCrew("crew-a");
    const root = await mount();
    expect(crewPick(root).value).toBe("crew-a");
    setCurrentCrew("crew-c");
    expect(crewPick(root).value).toBe("crew-c");
    setCurrentCrew(null);
    expect(crewPick(root).value).toBe("");
  });

  test("the meal list shows food names and a UTC clock time, not catalogue ids and ISO stamps", async () => {
    api.getFoodDay.mockResolvedValue(day([{
      meal_id: 7, eaten_at: "2026-11-15T09:05:00+00:00", crew: "crew-a",
      items: [{ food_id: "bar", servings: 2 }, { food_id: "retired-item", servings: 1 }],
    }]));
    const root = await mount();
    const meals = [...root.querySelectorAll("li")].map((li) => li.textContent);
    expect(meals).toContain("09:05 UTC: Cereal bar x 2, retired-item x 1");
    expect(root.textContent).not.toContain("2026-11-15T09:05");
  });
});
