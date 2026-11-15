import uPlot from "uplot";
import { getReadings, getReps, getSessions } from "../api";
import { COPY } from "../copy";
import type { CrewId, StoredReading } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { axisStamp, formatValue } from "../format";
import {
  LANES, bandSlices, bandTicks, laneLayout, laneRules, laneSeries, laneTag, setWork, sourceLine, statusOf, yRange,
  type BandSlice, type LaneSpec, type SetWork,
} from "../model/lanes";
import { RULES } from "../model/rules";
import { alpha, color } from "../palette";

// With bucket_s the hub keeps a few stored readings per bucket, so the whole window fits under LIMIT.
export const WINDOWS = [
  { key: "1h", hours: 1, bucketS: 10 },
  { key: "24h", hours: 24, bucketS: 180 },
  { key: "7d", hours: 7 * 24, bucketS: 1200 },
] as const;
const REFRESH_MS = 10_000;
export const LIMIT = 5000;
const SYNC_KEY = "lanes";
const fill = (status: string): string | undefined =>
  status === "ok" || status === "watch" || status === "act" ? alpha(color(status), status === "watch" ? 0.22 : 0.2) : undefined;


async function loadSets(sinceS: number, crew: CrewId | undefined): Promise<SetWork[]> {
  const sessions = (await getSessions()).filter(
    (s) => (crew === undefined || s.crew === crew) && (s.ended_at === null || Date.parse(s.ended_at) / 1000 >= sinceS),
  );
  const bodies = await Promise.all(sessions.map((s) => getReps(s.session)));
  return setWork(bodies).filter((w) => w.t >= sinceS);
}

export function shade(u: uPlot, slices: BandSlice[]): void {
  const { left, width } = u.bbox;
  const ymin = u.scales.y.min ?? 0;
  const ymax = u.scales.y.max ?? 0;
  u.ctx.save();
  for (const s of slices) {
    const f = fill(s.status);
    const lo = Math.max(s.lo, ymin);
    const hi = Math.min(s.hi, ymax);
    if (!f || hi <= lo) continue;
    const top = u.valToPos(hi, "y", true);
    u.ctx.fillStyle = f;
    u.ctx.fillRect(left, top, width, u.valToPos(lo, "y", true) - top);
  }
  u.ctx.restore();
}

export interface Prepared {
  spec: LaneSpec;
  layout: "chart" | "empty" | "hidden";
  x: number[];
  series: uPlot.Series[];
  data: (number | null)[][];
  slices: BandSlice[];
  y: [number, number] | null;
  value: string;
  status: string;
  tag: string;
  source: string;
  note: string;
}

const pts = (color: string, size: number, fill = color): uPlot.Series => ({
  stroke: "transparent", width: 0, points: { show: true, size, stroke: color, fill, width: 1.5 },
});

export function prepareReadings(spec: LaneSpec, rows: StoredReading[]): Prepared {
  const ind = spec.ind!;
  const rules = laneRules(RULES, ind, spec.window);
  const slices = bandSlices(rules);
  const s = laneSeries(rows, rules, spec.window);
  const line = color("series");
  const series: uPlot.Series[] = [{}, { stroke: line, width: s.mean ? 1 : 2, spanGaps: true, points: { show: false } }];
  const data: (number | null)[][] = [s.x, s.raw];
  if (s.mean) {
    series.push({ stroke: color("text"), width: 2.5, spanGaps: true, points: { show: false } });
    data.push(s.mean);
  }
  series.push(pts(color("watch"), 7), pts(color("act"), 9), pts(color("muted"), 7, "transparent"));
  data.push(s.watch, s.act, s.greyed);
  const judged = s.mean ?? s.raw;
  const lastAt = [...judged.keys()].reverse().find((i) => judged[i] !== null);
  const latest = rows.reduce<StoredReading | null>(
    (m, r) => (!m || Date.parse(r.measured_at) >= Date.parse(m.measured_at) ? r : m), null,
  );
  const lastRaw = [...s.raw].reverse().find((v) => v !== null) ?? null;
  let value = formatValue(ind, lastRaw, spec.unit);
  if (s.mean && lastAt !== undefined) value += ` · ${COPY["lanes.mean1h"]} ${formatValue(ind, judged[lastAt], spec.unit)}`;
  return {
    spec, layout: laneLayout(spec, rows.length), x: s.x, series, data, slices,
    y: yRange([...s.raw, ...(s.mean ?? []), ...s.greyed], slices),
    value, status: lastAt === undefined ? "unknown" : statusOf(rules, judged[lastAt] as number),
    tag: latest ? laneTag(ind, latest.src, latest.dev) : "", source: sourceLine(rules),
    note: s.mean ? COPY["lanes.meanNote"] : "",
  };
}

function prepareSets(spec: LaneSpec, sets: SetWork[]): Prepared {
  const last = sets[sets.length - 1];
  const top = sets.reduce((m, w) => Math.max(m, w.j), 0);
  return {
    spec, layout: laneLayout(spec, sets.length), x: sets.map((w) => w.t),
    series: [{}, pts(color("series"), 10)], data: [sets.map((w) => w.t), sets.map((w) => w.j)],
    slices: [], y: [0, top > 0 ? top * 1.2 : 1],
    value: last ? `${last.j.toFixed(1)} J · ${last.reps} ${COPY["lanes.reps"]}` : COPY["status.none"],
    status: "unknown", tag: last ? COPY["badge.camera"] : "", source: COPY["lanes.workSource"], note: "",
  };
}

/** uPlot options for one lane: shaded NASA bands, 24-hour UTC stamps, and the x range given (the chosen window). */
export function laneOptions(p: Prepared, o: { width: number; height: number; showX: boolean; x: [number, number] }): uPlot.Options {
  const stroke = color("muted");
  const grid = { stroke: color("line"), width: 1 };
  const ticks = p.y ? bandTicks(p.slices, p.y) : null;
  return {
    width: o.width, height: o.height, legend: { show: false },
    tzDate: (t) => uPlot.tzDate(new Date(t * 1000), "UTC"),
    cursor: { sync: { key: SYNC_KEY }, y: false, points: { show: false } },
    scales: { x: { time: true, range: () => o.x }, y: { range: (_u, lo, hi) => p.y ?? [lo, hi] } },
    axes: [
      { show: o.showX, stroke, grid, size: 30, values: (_u, splits) => splits.map((t) => axisStamp(t, o.x[1] - o.x[0])), label: COPY["lanes.utc"], labelSize: 16 },
      { stroke, grid, size: 56, ticks: { show: false }, ...(ticks ? { splits: () => ticks } : {}) },
    ],
    series: p.series,
    hooks: { drawClear: [(u) => shade(u, p.slices)] },
  };
}

/** The bucket step, or a warning when a lane still came back at the cap (a hub without bucket_s). */
export function footnote(rows: StoredReading[][], bucketS: number): string {
  if (rows.some((r) => r.length >= LIMIT)) return COPY["lanes.cut"];
  return COPY["lanes.step"].replace("{s}", bucketS < 60 ? `${bucketS} s` : `${bucketS / 60} min`);
}

export function renderLanes(root: HTMLElement): () => void {
  let hours: number = WINDOWS[1].hours;
  let plots: uPlot[] = [];
  let token = 0;
  let disposed = false;

  const picker = el("select", { id: "lanes-window" });
  for (const w of WINDOWS) picker.append(el("option", { value: String(w.hours), text: COPY[`lanes.w${w.key}`] }));
  picker.value = String(hours);
  const box = el("div", { class: "lanes" });
  const foot = el("div", { class: "footnote" });
  root.replaceChildren(
    el("div", { class: "lanes-bar" },
      el("label", { for: "lanes-window", text: `${COPY["lanes.window"]} ` }), picker,
      el("span", { class: "lanes-key" },
        el("i", { class: "sw sw-ok" }), COPY["lanes.keyOk"], el("i", { class: "sw sw-watch" }), COPY["lanes.keyWatch"],
        el("i", { class: "sw sw-act" }), COPY["lanes.keyAct"])),
    box, foot,
  );

  function draw(prepared: Prepared[], win: [number, number]) {
    plots.forEach((p) => p.destroy());
    plots = [];
    const shown = prepared.filter((p) => p.layout !== "hidden");
    const charts = shown.filter((p) => p.layout === "chart");
    const xr = charts.length ? win : null;
    const lastChart = charts[charts.length - 1];
    const width = Math.max(280, (root.clientWidth || 900) - 230);
    const rows: HTMLElement[] = [];
    for (const p of shown) {
      const head = el("div", { class: "lane-head" },
        el("div", { class: "lane-name", text: p.spec.label }),
        el("div", { class: `lane-val st-${p.status}`, text: p.value }),
        p.tag ? el("div", { class: "lane-tag", text: p.tag }) : null);
      const plotBox = el("div", { class: "lane-plot" });
      const src = el("div", { class: "lane-src", text: p.note ? `${p.source}. ${p.note}` : p.source });
      rows.push(el("div", { class: "lane", "data-lane": p.spec.key }, head, plotBox, src));
      if (p.layout === "empty" || !xr) {
        plotBox.append(el("div", { class: "lane-empty", text: COPY["lanes.empty"] }));
        continue;
      }
      plots.push(new uPlot(laneOptions(p, { width, height: p === lastChart ? 128 : 78, showX: p === lastChart, x: xr }),
        p.data as unknown as uPlot.AlignedData, plotBox));
    }
    box.replaceChildren(...rows);
  }

  async function load() {
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const sinceS = Date.now() / 1000 - hours * 3600;
    const since = new Date(sinceS * 1000).toISOString();
    const bucketS = WINDOWS.find((w) => w.hours === hours)!.bucketS;
    try {
      const [rows, sets] = await Promise.all([
        Promise.all(LANES.filter((l) => l.ind).map((l) => getReadings(l.ind!, { since, limit: LIMIT, crew, bucket_s: bucketS }))),
        loadSets(sinceS, crew),
      ]);
      if (disposed || mine !== token) return;
      let i = 0;
      draw(LANES.map((spec) => (spec.ind ? prepareReadings(spec, rows[i++]) : prepareSets(spec, sets))), [sinceS, Date.now() / 1000]);
      foot.textContent = footnote(rows, bucketS);
    } catch (e) {
      if (disposed || mine !== token) return;
      foot.textContent = e instanceof Error ? e.message : String(e);
    }
  }

  picker.addEventListener("change", () => {
    hours = Number(picker.value);
    void load();
  });
  const unsubCrew = onCrewChange(() => void load());
  const timer = setInterval(() => void load(), REFRESH_MS);
  void load();
  return () => {
    disposed = true;
    clearInterval(timer);
    unsubCrew();
    plots.forEach((p) => p.destroy());
  };
}
