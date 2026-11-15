import uPlot from "uplot";
import { getReps, getSessions } from "../api";
import { COPY } from "../copy";
import type { RepsBody, Session } from "../contract";
import { el } from "../dom";
import { formatTimeUtc } from "../format";
import { compareReps, nextSelected } from "../model/exercise";
import { color } from "../palette";

const POLL_MS = 2000;

const label = (s: Session) =>
  `${s.session} · ${s.camera_reps} camera / ${s.load_cell_reps} load-cell reps · ${
    s.ended_at ? `${COPY["exercise.ended"]} ${formatTimeUtc(s.ended_at)}` : COPY["exercise.running"]
  }`;

export function renderExercise(root: HTMLElement): () => void {
  let sessions: Session[] = [];
  const known: string[] = [];
  let selected: string | null = null;
  let plot: uPlot | null = null;
  let disposed = false;
  let lastBody: RepsBody | null = null;
  const finalPolled = new Set<string>();

  const picker = el("select", { id: "session-pick" });
  const summary = el("p", { "aria-live": "polite" });
  const chart = el("div");
  const table = el("table");
  root.replaceChildren(
    el("label", { for: "session-pick", text: `${COPY["exercise.pick"]} ` }), picker, summary, chart, table,
    el("p", { class: "footnote", text: COPY["camera.estimate"] }),
    el("p", { class: "footnote", text: COPY["work.note"] }),
    el("p", { class: "footnote", text: COPY["exercise.filterNote"] }),
    el("p", { class: "footnote", text: COPY["exercise.cellApprox"] }),
  );

  const num = (x: number | null, d = 1) => (x === null ? COPY["status.none"] : x.toFixed(d));
  const sign = (x: number | null, d = 1) => (x === null ? COPY["status.none"] : `${x >= 0 ? "+" : ""}${x.toFixed(d)}`);

  function drawBody(body: RepsBody) {
    lastBody = body;
    const { rows, summary: s } = compareReps(body);
    summary.textContent = s.comparable
      ? `n = ${s.paired} paired reps; mean difference ${sign(s.meanPeakDiffN)} N (${sign(s.meanPeakDiffPct)} %)`
      : (s.reason ?? "");
    const head = el("tr", {}, ...["Rep", COPY["exercise.cameraPeak"], COPY["exercise.cellPeak"], `${COPY["exercise.diff"]} (N)`, `${COPY["exercise.diff"]} (%)`, COPY["exercise.cameraWork"], `${COPY["exercise.cellWork"]} (${COPY["exercise.cellApprox"]})`, COPY["exercise.rom"]].map((t) => el("th", { text: t })));
    table.replaceChildren(head);
    for (const r of rows) {
      const camCell = el("td", { text: num(r.cameraPeakN) });
      if (r.cameraPeakN !== null) camCell.append(" ", el("span", { class: "chip estimate", text: "Estimate" }));
      if (r.replay) camCell.append(" ", el("span", { class: "chip", text: COPY["exercise.replay"] }));
      const cellCell = el("td", { text: num(r.cellPeakN) });
      if (r.cellPeakN !== null) cellCell.append(" ", el("span", { class: "chip", text: "Hobby sensor" }));
      table.append(el("tr", {}, el("td", { text: String(r.rep) }), camCell, cellCell, el("td", { text: sign(r.diffN) }), el("td", { text: sign(r.diffPct) }), el("td", { text: r.cameraWork }), el("td", { text: r.cellWork }), el("td", { text: r.romM })));
    }
    plot?.destroy();
    plot = null;
    if (rows.length) {
      const x = rows.map((r) => r.rep);
      plot = new uPlot(
        {
          width: Math.max(320, Math.min(900, root.clientWidth || 700)), height: 240,
          series: [{}, { label: COPY["exercise.chartCamera"], stroke: color("series"), width: 2, spanGaps: true }, { label: COPY["exercise.chartCell"], stroke: color("series-2"), width: 2, spanGaps: true }],
          axes: [{ stroke: color("text") }, { stroke: color("text") }],
        },
        [x, rows.map((r) => r.cameraPeakN), rows.map((r) => r.cellPeakN)] as unknown as uPlot.AlignedData,
        chart,
      );
    }
  }

  async function pollSessions() {
    try {
      const list = await getSessions();
      if (disposed) return;
      sessions = list;
      const next = nextSelected(selected, list, known);
      list.forEach((s) => known.includes(s.session) || known.push(s.session));
      picker.replaceChildren(...(list.length ? list : []).map((s) => el("option", { value: s.session, text: label(s) })));
      if (!list.length) summary.textContent = COPY["exercise.none"];
      if (next !== selected) { selected = next; void pollReps(); }
      if (selected) picker.value = selected;
    } catch (e) {
      summary.textContent = e instanceof Error ? e.message : String(e);
    }
  }

  async function pollReps() {
    if (!selected) return;
    try {
      const body = await getReps(selected);
      if (!disposed) drawBody(body);
    } catch {
      /* keep the last table */
    }
  }

  picker.addEventListener("change", () => { selected = picker.value; finalPolled.delete(selected); void pollReps(); });
  const timer = setInterval(() => {
    void pollSessions();
    const s = sessions.find((x) => x.session === selected);
    if (s && (!s.ended_at || !finalPolled.has(s.session))) {
      if (s.ended_at) finalPolled.add(s.session);
      void pollReps();
    }
  }, POLL_MS);
  void pollSessions();
  return () => { disposed = true; clearInterval(timer); plot?.destroy(); };
}
