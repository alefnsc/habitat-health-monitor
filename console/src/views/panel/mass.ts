import uPlot from "uplot";
import { COPY } from "../../copy";
import type { ExerciseDay, FoodDay, Session, StoredReading } from "../../contract";
import { el } from "../../dom";
import { formatTrainingWork } from "../../model/exercise";
import { foodEnergyLogged } from "../../model/food";
import { EXERCISES, exercisesDone } from "../../model/panel/exercises";
import { weighTrend } from "../../model/panel/trend";
import { color } from "../../palette";
import { card } from "./common";
import { copyFor, liveSource, type CardSource } from "./source";

export interface MassData {
  weighIns: StoredReading[] | null;
  food: FoodDay | null;
  training: ExerciseDay | null;
  sessions: Session[] | null;
}

/** Card 3: logged weigh-ins with their trend, food energy and training work side by side, today's exercises. */
export function massCard(src: CardSource = liveSource): { node: HTMLElement; update: (d: MassData) => void; dispose: () => void } {
  const c = card("p-mass", "3", COPY["panel.mass"]);
  let plot: uPlot | null = null;
  const chartBox = el("div");
  const update = (d: MassData) => {
    plot?.destroy();
    plot = null;
    const pts = (d.weighIns ?? []).filter((r) => r.q.every((f) => f === "ok"))
      .map((r) => ({ t: Date.parse(r.measured_at) / 1000, kg: r.val })).sort((a, b) => a.t - b.t);
    const { fit } = weighTrend(pts);
    const parts: (HTMLElement | null)[] = [el("div", { class: "kv", text: COPY["panel.massTitle"] })];
    if (!pts.length) {
      parts.push(el("p", { class: "note", text: copyFor(src, "panel.massNone") }));
    } else {
      parts.push(chartBox);
      parts.push(el("p", { class: "note", text: fit
        ? `${COPY["panel.trendSlope"].replace("{s}", `${fit.kgPerWeek >= 0 ? "+" : "−"}${Math.abs(fit.kgPerWeek).toFixed(2)}`)}. ${COPY["panel.trendNote"]}`
        : COPY["panel.trendNeeds"] }));
    }
    const done = exercisesDone(d.sessions ?? [], src.now());
    const side = el("div", { class: "side" },
      el("div", {}, el("div", { class: "lbl", text: `${COPY["food.energyTitle"]} · ${COPY["food.dayTitle"]}` }),
        el("div", { class: "val", text: d.food ? foodEnergyLogged(d.food) : COPY["status.none"] })),
      el("div", {}, el("div", { class: "lbl", text: COPY["food.trainTitle"] }),
        el("div", { class: "val", text: d.training?.camera_work_j != null ? formatTrainingWork(d.training.camera_work_j) : COPY["status.none"] })));
    const checks = el("ul", { class: "checks" }, ...EXERCISES.map((e) => el("li", { class: done.includes(e) ? "done" : "" },
      `${done.includes(e) ? "✓" : "○"} ${COPY[`panel.ex.${e}`]}`)));
    const excluded = d.training?.excluded_reps ?? 0;
    c.body.replaceChildren(...parts.filter((p): p is HTMLElement => !!p), side,
      ...(excluded > 0 ? [el("p", { class: "note", text: `${COPY["food.trainExcluded"]}${excluded}` })] : []),
      el("p", { class: "note", text: `${COPY["panel.sideNote"]} ${COPY["work.note"]}` }),
      el("div", { class: "kv", style: "margin-top:8px", text: COPY["panel.exercisesToday"] }), checks);
    if (!pts.length) return;
    const xs = [...new Set([...pts.map((p) => p.t), ...(fit ? [fit.line[0][0], fit.line[1][0], fit.extension[1][0]] : [])])].sort((a, b) => a - b);
    const at = (pairs: [number, number][], t: number) => pairs.find((p) => p[0] === t)?.[1] ?? null;
    const dots = xs.map((t) => pts.find((p) => p.t === t)?.kg ?? null);
    const line = xs.map((t) => (fit ? at(fit.line, t) : null));
    const ext = xs.map((t) => (fit ? at(fit.extension, t) : null));
    const stroke = color("muted");
    const grid = { stroke: color("line"), width: 1 };
    const width = Math.max(240, (c.node.clientWidth || 420) - 30);
    plot = new uPlot({
      width, height: 130, legend: { show: false }, cursor: { show: false },
      tzDate: (t) => uPlot.tzDate(new Date(t * 1000), "UTC"),
      scales: { x: { time: true } },
      axes: [{ stroke, grid, size: 26 }, { stroke, grid, size: 44 }],
      series: [{},
        { stroke: "transparent", width: 0, points: { show: true, size: 8, stroke: color("series"), fill: color("series") } },
        { stroke: color("text-2"), width: 2, spanGaps: true, points: { show: false } },
        { stroke: color("text-2"), width: 2, dash: [6, 5], spanGaps: true, points: { show: false } }],
    }, [xs, dots, line, ext] as unknown as uPlot.AlignedData, chartBox);
  };
  return { node: c.node, update, dispose: () => plot?.destroy() };
}
