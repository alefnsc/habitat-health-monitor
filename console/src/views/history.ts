import uPlot from "uplot";
import { getReadings } from "../api";
import { COPY } from "../copy";
import type { Ind, StoredReading } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { sourceKindLabel } from "../format";
import { defaultWindow, moodSleepSeries, thresholdLines, toSeries, type ThresholdRule } from "../model/history";
import { board } from "../state";
import { RULES } from "../model/rules";
import { color } from "../palette";

export { RULES };

export const HISTORY_INDS: Ind[] = [
  "hr", "spo2", "skin_temp", "body_temp", "bp_sys", "bp_dia", "glucose", "sleep_h", "mood",
  "cabin_ppco2", "cabin_temp", "cabin_rh", "cabin_p", "cabin_lux", "cabin_co2",
];
const MOOD_SLEEP = "mood_sleep";
const LABEL: Record<string, string> = {
  hr: "Heart rate", spo2: "SpO2", skin_temp: "Skin temperature", body_temp: "Body temperature", bp_sys: "Systolic",
  bp_dia: "Diastolic", glucose: "Glucose", sleep_h: "Sleep", mood: "Mood", cabin_ppco2: "Cabin CO2 partial pressure",
  cabin_temp: "Cabin temperature", cabin_rh: "Cabin humidity", cabin_p: "Cabin pressure", cabin_lux: "Cabin light",
  cabin_co2: "Cabin CO2 concentration", [MOOD_SLEEP]: COPY["history.moodSleep"],
};

export function indFromHash(hash: string): string {
  const seg = hash.replace(/^#\/?/, "").split("/")[1];
  return seg && (HISTORY_INDS as string[]).concat(MOOD_SLEEP).includes(seg) ? seg : "hr";
}


export function renderHistory(root: HTMLElement): () => void {
  let ind = indFromHash(location.hash);
  let plot: uPlot | null = null;
  let loadedFor = "";
  let lastX = 0;
  let rows: StoredReading[] = [];
  let disposed = false;

  const picker = el("select", { id: "history-ind" });
  for (const i of [...HISTORY_INDS, MOOD_SLEEP]) picker.append(el("option", { value: i, text: LABEL[i] }));
  picker.value = ind;
  const chartBox = el("div", { class: "chart" });
  const foot = el("div", { class: "footnote" });
  root.replaceChildren(
    el("label", { for: "history-ind", text: `${COPY["history.pick"]} ` }), picker, chartBox, foot,
  );

  const width = () => Math.max(320, Math.min(1100, (root.clientWidth || 800) - 8));
  const base = (series: uPlot.Series[], data: uPlot.AlignedData, axes?: uPlot.Axis[]) => {
    plot?.destroy();
    const stroke = color("text");
    plot = new uPlot(
      {
        width: width(), height: 320, tzDate: (ts) => uPlot.tzDate(new Date(ts * 1000), "UTC"), series,
        axes: axes ?? [{ stroke }, { stroke }],
      },
      data, chartBox,
    );
  };

  async function load() {
    const crew = currentCrew() ?? undefined;
    const token = `${ind}|${crew ?? ""}`;
    loadedFor = token;
    chartBox.replaceChildren();
    foot.replaceChildren();
    try {
      if (ind === MOOD_SLEEP) {
        const w = defaultWindow("mood");
        const since = new Date(Date.now() - w.sinceIsoOffsetH * 3600e3).toISOString();
        const [mood, sleep] = await Promise.all([
          getReadings("mood", { since, limit: w.limit, crew }), getReadings("sleep_h", { since, limit: w.limit, crew }),
        ]);
        if (disposed || loadedFor !== token) return;
        const s = moodSleepSeries(mood, sleep);
        base(
          [{}, { label: "Mood (1-5)", stroke: color("series"), width: 2, scale: "mood", spanGaps: true },
            { label: "Sleep (h)", stroke: color("series-2"), width: 2, scale: "sleep", spanGaps: true }],
          [s.x, s.mood, s.sleep],
          [{ stroke: color("text") }, { scale: "mood", stroke: color("series") }, { scale: "sleep", side: 1, stroke: color("series-2") }],
        );
        foot.textContent = COPY["history.moodNote"];
        return;
      }
      const w = defaultWindow(ind as Ind);
      const since = new Date(Date.now() - w.sinceIsoOffsetH * 3600e3).toISOString();
      const got = await getReadings(ind as Ind, { since, limit: w.limit, crew });
      if (disposed || loadedFor !== token) return;
      rows = got;
      draw();
    } catch (e) {
      foot.textContent = e instanceof Error ? e.message : String(e);
    }
  }

  function draw() {
    const s = toSeries(rows);
    lastX = s.x.length ? s.x[s.x.length - 1] : 0;
    const { lines, skipped } = thresholdLines(RULES, ind as Ind);
    const series: uPlot.Series[] = [
      {},
      { label: LABEL[ind], stroke: color("series"), width: 2, spanGaps: true, points: { show: true } },
      { label: "Not assessed", stroke: "transparent", width: 0, points: { show: true, stroke: color("muted"), fill: "transparent", width: 1.5, size: 7 } },
    ];
    const data: (number | null)[][] = [s.x, s.assessed, s.greyed];
    for (const l of lines) {
      series.push({ label: l.label, stroke: color("watch"), width: 1, dash: [6, 4], points: { show: false } });
      data.push(s.x.map(() => l.y));
    }
    base(series, data as unknown as uPlot.AlignedData);
    const kinds = [...new Set(RULES.filter((r) => r.ind === ind && lines.some((l) => l.label.startsWith(r.id))).map((r) => sourceKindLabel(r.source_kind)))];
    foot.replaceChildren(
      el("div", { text: COPY["history.greyedNote"] }),
      ...(kinds.length ? [el("div", { text: kinds.join("; ") })] : []),
      ...skipped.map((id) => el("div", { text: `${id}: ${COPY["history.skipped"]}` })),
    );
  }

  const unsubBoard = board.subscribe(() => {
    if (ind === MOOD_SLEEP || !plot) return;
    const e = board.entries.find((x) => x.ind === ind);
    if (!e) return;
    const t = Date.parse(e.measured_at) / 1000;
    if (t <= lastX) return;
    rows = [...rows, { ...e, v: 1, boot: 0, seq: 0, age_ms: 0, id: e.reading_id, received_at: e.measured_at, derived_from: null } as unknown as StoredReading];
    draw();
  });
  const unsubCrew = onCrewChange(() => void load());
  picker.addEventListener("change", () => {
    ind = picker.value;
    history.replaceState(null, "", `#/history/${ind}`);
    void load();
  });
  void load();
  return () => {
    disposed = true;
    unsubBoard();
    unsubCrew();
    plot?.destroy();
  };
}
