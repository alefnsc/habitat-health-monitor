import uPlot from "uplot";
import { COPY } from "../../copy";
import type { Ind, IssCabin, StatusEntry, StoredReading } from "../../contract";
import { el } from "../../dom";
import { devLabel, formatAge, formatValue, statusClass, statusLabel } from "../../format";
import { LANES, laneRules, type LaneSpec } from "../../model/lanes";
import { bandSentence, compactSource } from "../../model/panel/bands";
import { latestEntry } from "../../model/panel/latest";
import { missingLine } from "../../model/panel/missing";
import { RULES } from "../../model/rules";
import { laneOptions, prepareReadings } from "../lanes";
import { card, pill } from "./common";
import { liveSource, type PanelClock } from "./source";

export const PANEL_LANES: LaneSpec[] = ["cabin_temp", "cabin_rh", "cabin_ppco2", "hr", "spo2", "sleep_h"]
  .map((k) => LANES.find((l) => l.key === k)!);

export interface VitalsData {
  rows: Record<string, StoredReading[]> | null;
  win: [number, number];
  iss: IssCabin | null;
  /** Latest status entries, for lanes whose window is empty (a delayed cloud sync can be days old). */
  latest?: StatusEntry[] | null;
}

function issNow(iss: IssCabin | null, ind: Ind): string | null {
  if (ind !== "cabin_temp" || !iss) return null;
  const it = iss.items.find((i) => i.name === "cabin_temperature" && !i.stale);
  return it ? `${COPY["panel.issNow"]} ${formatValue("cabin_temp", it.val, "C")}` : null;
}

/** Card 4: compact lanes against the NASA bands, and what this bench cannot fill. */
export function vitalsCard(src: PanelClock = liveSource): { node: HTMLElement; update: (d: VitalsData) => void; dispose: () => void } {
  const c = card("p-vitals", "4", COPY["panel.vitals"]);
  c.sub.textContent = `${COPY[src.replay ? "panel.windowReplay" : "panel.window"]} · ${COPY["lanes.utc"]}`;
  let plots: uPlot[] = [];
  const update = (d: VitalsData) => {
    plots.forEach((p) => p.destroy());
    plots = [];
    if (!d.rows) {
      c.body.replaceChildren(el("p", { class: "note", text: COPY["panel.noData"] }));
      return;
    }
    const shown = PANEL_LANES.filter((s) => (d.rows![s.key] ?? []).length > 0);
    // A lane with nothing in the window still shows its newest reading, with its source and age, before it counts as missing.
    const older = PANEL_LANES.filter((s) => !shown.includes(s))
      .map((s) => ({ spec: s, e: latestEntry(d.latest, s.ind as Ind) }))
      .filter((x): x is { spec: LaneSpec; e: StatusEntry } => x.e !== null);
    const empty = PANEL_LANES.filter((s) => !shown.includes(s) && !older.some((o) => o.spec === s)).map((s) => s.ind as Ind);
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
    for (const { spec, e } of older) {
      const cls = statusClass(e.status, e.q);
      const age = formatAge((src.now() - Date.parse(e.measured_at)) / 1000);
      rows.push(el("div", { class: "vlane older", "data-lane": spec.key },
        el("div", {},
          el("div", { class: "name", text: spec.label }),
          el("div", {}, el("span", { class: `val st-${cls}`, text: formatValue(e.ind, e.val, e.unit) }), " ", pill(cls, statusLabel(e.status, e.q))),
          el("div", { class: "src", text: [compactSource(laneRules(RULES, spec.ind as Ind, spec.window)), devLabel(e.dev)].join(" · ") })),
        el("div", { class: "why", text: `${COPY["panel.olderThanWindow"]} ${age}.` })));
    }
    const parts: HTMLElement[] = [...rows];
    const miss = missingLine(empty, src.replay ? COPY["panel.notInReplay"] : undefined);
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
