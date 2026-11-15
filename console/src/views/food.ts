import { ApiError, getExerciseDay, getFoodCatalog, getFoodDay, getFoodReferences, postFoodLog } from "../api";
import { COPY } from "../copy";
import type { ExerciseDay, FoodCatalog, FoodDay, FoodReferences, IntakeInd } from "../contract";
import { INTAKE_INDS } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { sourceKindLabel, statusClass } from "../format";
import { formatTrainingWork } from "../model/exercise";
import {
  NUTRIENT_LABEL, buildMealRequest, formatNutrient, mealPreview, reportedBy, validSelection, type Selection,
} from "../model/food";
import { packScanner } from "./scan";

const msg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : String(e));

export function totalsTable(day: FoodDay): HTMLElement {
  const table = el("table", { class: "food-totals" });
  table.append(
    el("thead", {}, el("tr", {},
      el("th", { text: COPY["food.colNutrient"] }), el("th", { text: COPY["food.colTotal"] }),
      el("th", { text: COPY["food.colStatus"] }))),
  );
  const body = el("tbody");
  for (const ind of INTAKE_INDS) {
    const t = day.totals[ind];
    const label = ind === "intake_kcal" ? COPY["food.energyTitle"] : NUTRIENT_LABEL[ind];
    const cls = statusClass(t.status, []);
    const status = el("td", { class: `tile ${cls}`, text: COPY[`status.${t.status}`] });
    if (t.source_ref) status.append(el("div", { class: "footnote", text: `${sourceKindLabel(t.source_kind)}: ${t.source_ref}` }));
    if (t.floor_judged === false) status.append(el("div", { class: "footnote", text: COPY["food.floorNotJudged"] }));
    body.append(
      el("tr", { "data-ind": ind }, el("td", { text: label }),
        el("td", { text: formatNutrient(ind, t.val) }, el("div", { class: "footnote", text: t.meals_total === 0 && t.val === null ? COPY["food.notReported"] : reportedBy(t) })),
        status),
    );
  }
  table.append(body);
  return table;
}

export function trainingBox(d: ExerciseDay): HTMLElement {
  const box = el("section", { class: "food-train" }, el("h3", { text: COPY["food.trainTitle"] }), el("p", { class: "footnote", text: COPY["food.trainNote"] }));
  if (d.camera_reps === 0 && d.cell_work_j === null) {
    box.append(el("p", { text: COPY["food.trainNone"] }));
    return box;
  }
  const work = (j: number | null) => (j === null ? COPY["status.none"] : formatTrainingWork(j));
  box.append(
    el("ul", {},
      el("li", { text: `${COPY["food.trainSessions"]}: ${d.sessions}` }),
      el("li", { text: `${COPY["food.trainReps"]}: ${d.camera_reps}` }),
      el("li", { text: `${COPY["food.trainCameraWork"]}: ${work(d.camera_work_j)}` }),
      el("li", { text: `${COPY["food.trainCellWork"]}: ${work(d.cell_work_j)}` }),
    ),
  );
  if (d.replay) box.append(el("p", { class: "footnote", text: COPY["food.trainReplay"] }));
  if (d.excluded_reps > 0) box.append(el("p", { class: "footnote", text: `${COPY["food.trainExcluded"]}${d.excluded_reps}` }));
  return box;
}

export function referencesBox(refs: FoodReferences): HTMLElement {
  const box = el("section", { class: "food-refs" }, el("h3", { text: COPY["food.refTitle"] }), el("p", { class: "footnote", text: COPY["food.refNote"] }));
  const list = el("ul");
  for (const r of refs.items) {
    const li = el("li", {}, `${r.label}: ${r.value_text}`);
    if (r.sex_note) li.append(` (${r.sex_note})`);
    li.append(" ", el("a", { href: r.url, rel: "noopener", text: `${COPY["food.sourceLink"]}: ${r.source_ref}` }));
    list.append(li);
  }
  box.append(list, ...refs.notes.map((n) => el("p", { class: "footnote", text: n })));
  return box;
}

export function renderFood(root: HTMLElement): () => void {
  let disposed = false;
  let catalog: FoodCatalog | null = null;
  const sel: Selection = [];
  const err = el("p", { class: "err", role: "alert" });
  const notice = el("p", { class: "footnote" });
  const dayBox = el("section");
  const refBox = el("section");
  const trainBox = el("section");
  const draft = el("ul");
  const draftSums = el("p", { class: "footnote" });
  const picker = el("select", { id: "food-item" });
  const servings = el("input", { id: "food-servings", type: "number", min: 0.5, max: 20, step: 0.5, value: 1 });
  const add = el("button", { type: "button", text: COPY["food.addItem"] });
  const log = el("button", { type: "button", text: COPY["food.logMeal"] });
  const scanner = packScanner(() => catalog, (id) => {
    picker.value = id;
    const item = catalog?.items.find((x) => x.id === id);
    notice.textContent = `${COPY["food.scanPicked"]}${item?.name ?? id}. ${COPY["food.scanNext"]}`;
    servings.focus();
  });

  root.replaceChildren(
    el("p", { class: "footnote", text: COPY["food.disclaimer"] }),
    err,
    el("section", {}, el("h3", { text: COPY["food.logTitle"] }),
      el("label", { for: "food-item", text: `${COPY["food.pickItem"]} ` }), picker, " ",
      el("label", { for: "food-servings", text: `${COPY["food.servings"]} ` }), servings, " ", add, scanner.node, draft, draftSums, log, notice),
    el("h3", { text: COPY["food.dayTitle"] }), dayBox,
    trainBox,
    refBox,
  );

  const showDraft = () => {
    draft.replaceChildren();
    sel.forEach((s, i) => {
      const item = catalog?.items.find((x) => x.id === s.food_id);
      const rm = el("button", { type: "button", text: COPY["food.removeItem"] });
      rm.addEventListener("click", () => {
        sel.splice(i, 1);
        showDraft();
      });
      draft.append(el("li", {}, `${item?.name ?? s.food_id} x ${s.servings} (${item?.serving_label ?? ""}) `, rm));
    });
    if (!catalog || sel.length === 0) {
      draftSums.textContent = "";
      return;
    }
    const p = mealPreview(catalog, sel);
    draftSums.textContent = INTAKE_INDS.map((i: IntakeInd) => `${NUTRIENT_LABEL[i]}: ${formatNutrient(i, p[i])}`).join("; ");
  };

  const loadDay = async () => {
    try {
      const crew = currentCrew() ?? undefined;
      const day = await getFoodDay(crew);
      if (disposed) return;
      const mealsList = el("ul");
      for (const m of day.meals) mealsList.append(el("li", { text: `${m.eaten_at}: ${m.items.map((i) => `${i.food_id} x ${i.servings}`).join(", ")}` }));
      const parts: (Node | null)[] = [
        day.crew === null ? el("p", { class: "footnote", text: COPY["food.allCrewNote"] }) : null,
        totalsTable(day),
        day.body_mass !== null ? el("p", { text: `${COPY["food.bodyMass"]}: ${day.body_mass.toFixed(1)} kg` }) : null,
        el("p", { class: "footnote", text: COPY["food.alertsNote"] }),
        el("h4", { text: COPY["food.mealsTitle"] }),
        day.meals.length ? mealsList : el("p", { class: "footnote", text: COPY["food.noMeals"] }),
      ];
      dayBox.replaceChildren(...parts.filter((n): n is Node => n !== null));
    } catch (e) {
      if (!disposed) err.textContent = COPY["food.loadError"] + msg(e);
    }
  };

  const loadTraining = async () => {
    try {
      const d = await getExerciseDay(currentCrew() ?? undefined);
      if (!disposed) trainBox.replaceChildren(trainingBox(d));
    } catch {
      /* training is optional: the food screen works without it */
    }
  };

  void (async () => {
    void loadTraining();
    try {
      const [c, r] = await Promise.all([getFoodCatalog(), getFoodReferences().catch(() => null)]);
      if (disposed) return;
      catalog = c;
      for (const i of c.items) picker.append(el("option", { value: i.id, text: `${i.name} (${i.serving_label})` }));
      if (r) refBox.replaceChildren(referencesBox(r));
    } catch (e) {
      err.textContent = COPY["food.loadError"] + msg(e);
    }
    await loadDay();
  })();

  add.addEventListener("click", () => {
    const n = Number(servings.value);
    if (!picker.value || !(n > 0)) return;
    sel.push({ food_id: picker.value, servings: n });
    showDraft();
  });
  log.addEventListener("click", async () => {
    err.textContent = "";
    if (!validSelection(sel)) {
      notice.textContent = COPY["food.mealEmpty"];
      return;
    }
    try {
      const r = await postFoodLog(buildMealRequest(currentCrew(), sel));
      sel.length = 0;
      showDraft();
      notice.textContent = COPY["food.mealLogged"] + (r.not_reported.length ? `. ${COPY["food.notReportedNote"]}${r.not_reported.map((i) => NUTRIENT_LABEL[i as IntakeInd]).join(", ")}` : "");
      await loadDay();
    } catch (e) {
      err.textContent = msg(e);
    }
  });
  const off = onCrewChange(() => {
    void loadDay();
    void loadTraining();
  });
  return () => {
    disposed = true;
    scanner.stop();
    off();
  };
}
