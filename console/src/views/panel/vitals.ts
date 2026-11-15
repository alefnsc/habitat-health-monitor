import uPlot from "uplot";
import { COPY } from "../../copy";
import type { Ind, IssCabin, StoredReading } from "../../contract";
import { el } from "../../dom";
import { formatValue } from "../../format";
import { LANES, laneRules, type LaneSpec } from "../../model/lanes";
import { bandSentence, compactSource } from "../../model/panel/bands";
import { missingLine } from "../../model/panel/missing";
import { RULES } from "../../model/rules";
import { laneOptions, prepareReadings } from "../lanes";
import { card, pill } from "./common";
import { copyFor, liveSource, type CardSource } from "./source";

export const PANEL_LANES: LaneSpec[] = ["cabin_temp", "cabin_rh", "cabin_ppco2", "hr", "spo2", "sleep_h"]
  .map((k) => LANES.find((l) => l.key === k)!);

export interface VitalsData {
  rows: Record<string, StoredReading[]> | null;
  win: [number, number];
  iss: IssCabin | null;
}

function issNow(iss: IssCabin | null, ind: Ind): string | null {
  if (ind !== "cabin_temp" || !iss) return null;
  const it = iss.items.find((i) => i.name === "cabin_temperature" && !i.stale);
  return it ? `${COPY["panel.issNow"]} ${formatValue("cabin_temp", it.val, "C")}` : null;
}

/** Card 4: compact lanes against the NASA bands, and what this bench cannot fill. */
export function vitalsCard(src: CardSource = liveSource): { node: HTMLElement; update: (d: VitalsData) => void; dispose: () => void } {
  const c = card("p-vitals", "4", COPY["panel.vitals"]);
  c.sub.textContent = `${copyFor(src, "panel.window")} · ${COPY["lanes.utc"]}`;
  let plots: uPlot[] = [];
  const update = (d: VitalsData) => {
    plots.forEach((p) => p.destroy());
    plots = [];
    if (!d.rows) {
      c.body.replaceChildren(el("p", { class: "note", text: COPY["panel.noData"] }));
      return;
    }
    const shown = PANEL_LANES.filter((s) => (d.rows![s.key] ?? []).length > 0);
    const empty = PANEL_LANES.filter((s) => !shown.includes(s)).map((s) => s.ind as Ind);
    const rows: HTMLElement[] = [];
    const pending: { box: HTMLElement; p: ReturnType<typeof prepareReadings>; last: boolean }[] = [];
    shown.forEach((spec, i) => {
      const p = prepareReadings(spec, d.rows![spec.key]);
      const lastRaw = [...p.data[1]].reverse().find((v) => v !== null) ?? null;
      const why = lastRaw === null ? null : bandSentence(RULES, spec.ind as Ind, lastRaw);
      const iss = issNow(d.iss, spec.ind as Ind);
      const box = el("div", { class: "lane-plot" });
      rows.push(el("div", { class: "vlane", "data-lane": spec.key },
        el("div", {},
          el("div", { class: "name", text: spec.label }),
          el("div", {}, el("span", { class: `val st-${p.status}`, text: p.value }), " ", pill(p.status, COPY[`status.${p.status}`])),
          why ? el("div", { class: "why", text: why }) : null,
          iss ? el("span", { class: "pchip", text: iss }) : null,
          el("div", { class: "src", text: [compactSource(laneRules(RULES, spec.ind as Ind, spec.window)), p.tag].filter(Boolean).join(" · ") })),
        box));
      pending.push({ box, p, last: i === shown.length - 1 });
    });
    const parts: HTMLElement[] = [...rows];
    const miss = missingLine(empty, copyFor(src, "panel.notOnBench"));
    if (miss) parts.push(el("p", { class: "note", text: miss }));
    c.body.replaceChildren(...parts);
    for (const { box, p, last } of pending) {
      const width = Math.max(260, (c.node.clientWidth || 1100) - 342);
      plots.push(new uPlot(laneOptions(p, { width, height: last ? 84 : 54, showX: last, x: d.win }),
        p.data as unknown as uPlot.AlignedData, box));
    }
  };
  return { node: c.node, update, dispose: () => plots.forEach((p) => p.destroy()) };
}
