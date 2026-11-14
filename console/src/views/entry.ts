import { ApiError, postReading } from "../api";
import { COPY } from "../copy";
import type { CrewId, ReadingMessage, StatusEntry, SymptomCode } from "../contract";
import { el } from "../dom";
import { formatTimeUtc } from "../format";
import { ENTRY_BOUNDS, buildManualReadings, createSequencer, type ManualInput, type Sequencer } from "../payload";
import { board } from "../state";
import { currentCrew } from "../crew";

export const ENTRY_ROWS = ["bp", "hr", "spo2", "body_temp", "glucose", "sleep_h", "mood", "symptom", "body_mass"] as const;
export type EntryRow = (typeof ENTRY_ROWS)[number];

export function defaultSrc(row: EntryRow): "certified" | "self" {
  return row === "sleep_h" || row === "mood" || row === "symptom" || row === "body_mass" ? "self" : "certified";
}

export interface FailedSend {
  ind: string;
  error: string;
  message: ReadingMessage | null;
}

export type SubmitResult = { sent: number; results: StatusEntry[]; failed: FailedSend[] };
type Post = typeof postReading;
export type RowInput = ManualInput & { src?: "certified" | "self" };

const errText = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : String(e));

async function sendAll(messages: ReadingMessage[], post: Post): Promise<SubmitResult> {
  const out: SubmitResult = { sent: 0, results: [], failed: [] };
  for (const m of messages) {
    try {
      const r = await post(m);
      out.sent += 1;
      out.results.push(...r.results);
    } catch (e) {
      out.failed.push({ ind: m.ind, error: errText(e), message: m });
    }
  }
  return out;
}

export async function submitAll(
  rows: RowInput[],
  crew: CrewId | null,
  seq: Sequencer,
  post: Post,
): Promise<SubmitResult> {
  if (crew === null) {
    return { sent: 0, results: [], failed: [{ ind: "*", error: COPY["crew.choose"], message: null }] };
  }
  const messages: ReadingMessage[] = [];
  const buildFailed: FailedSend[] = [];
  for (const row of rows) {
    const rowKey = row.ind as EntryRow;
    const r = buildManualReadings(row, crew, row.src ?? defaultSrc(rowKey), seq);
    if (r.ok) messages.push(...r.messages);
    else buildFailed.push({ ind: row.ind, error: r.error, message: null });
  }
  const sent = await sendAll(messages, post);
  return { ...sent, failed: [...buildFailed, ...sent.failed] };
}

export async function resendFailed(failed: FailedSend[], post: Post): Promise<SubmitResult> {
  const retryable = failed.filter((f) => f.message !== null).map((f) => f.message as ReadingMessage);
  const kept = failed.filter((f) => f.message === null);
  const sent = await sendAll(retryable, post);
  return { ...sent, failed: [...kept, ...sent.failed] };
}

// ---- DOM renderer (checked by hand in a browser) ----

const SYMPTOMS: { code: SymptomCode; label: string }[] = [
  { code: "headache", label: "Headache" },
  { code: "fatigue", label: "Fatigue" },
  { code: "nausea", label: "Nausea" },
  { code: "poor_sleep", label: "Poor sleep" },
  { code: "none", label: COPY["entry.symptomNone"] },
];

const ROW_LABEL: Record<EntryRow, string> = {
  bp: "Blood pressure (mmHg)",
  hr: "Heart rate (bpm)",
  spo2: "SpO2 (%)",
  body_temp: "Body temperature (°C)",
  glucose: "Glucose (mg/dL)",
  sleep_h: "Sleep (hours)",
  mood: "Mood",
  symptom: "Symptoms",
  body_mass: "Body mass (kg)",
};

const rowOfInd = (ind: string): string => (ind === "bp_sys" || ind === "bp_dia" ? "bp" : ind);

export function renderEntry(root: HTMLElement): void {
  const seq = createSequencer(Math.floor(Date.now() / 1000));
  const failedByRow = new Map<string, FailedSend[]>();
  root.replaceChildren();
  const form = el("form", { class: "entry", novalidate: true });
  const topErr = el("div", { class: "err", role: "alert" });
  const status = new Map<string, HTMLElement>();
  const readers = new Map<EntryRow, () => RowInput | null>();
  const clearers = new Map<string, () => void>();

  const numInput = (id: string, ind: "hr" | "spo2" | "body_temp" | "bp_sys" | "bp_dia" | "glucose" | "sleep_h" | "body_mass") => {
    const b = ENTRY_BOUNDS[ind];
    return el("input", { id, type: "number", min: b.min, max: b.max, step: b.step, inputmode: "decimal" });
  };
  const srcSelect = (id: string, row: EntryRow) => {
    const sel = el("select", { id });
    sel.append(el("option", { value: "certified", text: COPY["entry.certified"] }), el("option", { value: "self", text: COPY["entry.self"] }));
    sel.value = defaultSrc(row);
    return sel;
  };
  const addRow = (row: EntryRow, control: (Node | string)[], labelFor: string) => {
    const msg = el("span", { class: "row-msg", "aria-live": "polite" });
    status.set(row, msg);
    form.append(el("div", { class: "row" }, el("label", { for: labelFor, text: ROW_LABEL[row] }), el("div", {}, ...control, msg)));
  };
  const num = (inp: HTMLInputElement) => (inp.value.trim() === "" ? null : Number(inp.value));

  // bp
  {
    const sys = numInput("in-bp-sys", "bp_sys");
    const dia = numInput("in-bp-dia", "bp_dia");
    sys.setAttribute("aria-label", "Systolic");
    dia.setAttribute("aria-label", "Diastolic");
    const src = srcSelect("in-bp-src", "bp");
    addRow("bp", [sys, " / ", dia, " ", el("label", { for: "in-bp-src", text: `${COPY["entry.measuredWith"]} ` }), src], "in-bp-sys");
    readers.set("bp", () => {
      const s = num(sys), d = num(dia);
      if (s === null && d === null) return null;
      return { ind: "bp", sys: s ?? NaN, dia: d ?? NaN, src: src.value as "certified" | "self" };
    });
    clearers.set("bp", () => { sys.value = ""; dia.value = ""; });
  }
  for (const ind of ["hr", "spo2", "body_temp", "glucose", "sleep_h", "body_mass"] as const) {
    const inp = numInput(`in-${ind}`, ind);
    const controls: HTMLElement[] = [inp];
    let src: HTMLSelectElement | null = null;
    if (defaultSrc(ind) === "certified" || ind === "body_mass") {
      src = srcSelect(`in-${ind}-src`, ind);
      controls.push(el("label", { for: `in-${ind}-src`, text: ` ${COPY["entry.measuredWith"]} ` }), src);
    }
    addRow(ind, controls, `in-${ind}`);
    readers.set(ind, () => {
      const v = num(inp);
      if (v === null) return null;
      return { ind, val: v, src: (src?.value ?? "self") as "certified" | "self" };
    });
    clearers.set(ind, () => { inp.value = ""; });
  }
  // mood
  {
    const group = el("div", { role: "radiogroup", "aria-label": "Mood" });
    for (let n = 1; n <= 5; n++) {
      group.append(el("label", {}, el("input", { type: "radio", name: "mood", value: String(n) }), ` ${n} `));
    }
    group.append(el("div", { class: "footnote", text: COPY["entry.moodHelp"] }));
    addRow("mood", [group], "in-mood");
    readers.set("mood", () => {
      const c = group.querySelector<HTMLInputElement>("input:checked");
      return c ? { ind: "mood", val: Number(c.value) } : null;
    });
    clearers.set("mood", () => group.querySelectorAll<HTMLInputElement>("input").forEach((i) => { i.checked = false; }));
  }
  // symptoms
  {
    const group = el("div", { role: "group", "aria-label": "Symptoms" });
    const boxes = new Map<SymptomCode, HTMLInputElement>();
    for (const s of SYMPTOMS) {
      const cb = el("input", { type: "checkbox", value: s.code });
      boxes.set(s.code, cb);
      cb.addEventListener("change", () => {
        if (!cb.checked) return;
        if (s.code === "none") boxes.forEach((o, k) => { if (k !== "none") o.checked = false; });
        else boxes.get("none")!.checked = false;
      });
      group.append(el("label", {}, cb, ` ${s.label} `));
    }
    addRow("symptom", [group], "in-symptom");
    readers.set("symptom", () => {
      const codes = [...boxes].filter(([, b]) => b.checked).map(([c]) => c);
      return codes.length ? { ind: "symptom", codes } : null;
    });
    clearers.set("symptom", () => boxes.forEach((b) => { b.checked = false; }));
  }
  form.append(el("div", { class: "footnote", text: COPY["entry.bodyMassNote"] }));

  const send = el("button", { type: "submit", class: "primary", text: COPY["entry.send"] });
  form.append(topErr, send);

  const showRow = (row: string, kind: "ok" | "err", text: string, retry?: () => void) => {
    const n = status.get(row);
    if (!n) return;
    n.replaceChildren(el("span", { class: kind === "ok" ? "ok-msg" : "err", text }));
    if (retry) {
      const b = el("button", { type: "button", text: COPY["entry.retry"] });
      b.addEventListener("click", retry);
      n.append(" ", b);
    }
  };
  const applyOutcome = (sentRows: string[], r: SubmitResult) => {
    board.apply(r.results);
    topErr.textContent = "";
    failedByRow.clear();
    for (const f of r.failed) {
      if (f.ind === "*") { topErr.textContent = f.error; continue; }
      const key = rowOfInd(f.ind);
      failedByRow.set(key, [...(failedByRow.get(key) ?? []), f]);
    }
    const stamp = formatTimeUtc(new Date().toISOString());
    if (r.failed.some((f) => f.ind === "*")) return;
    for (const row of sentRows) {
      const fails = failedByRow.get(row);
      if (!fails) {
        showRow(row, "ok", `${COPY["entry.sent"]} ${stamp}`);
        clearers.get(row)?.();
      } else {
        showRow(row, "err", fails[0].error, fails.some((f) => f.message) ? () => retryRow(row) : undefined);
      }
    }
  };
  const retryRow = async (row: string) => {
    const fails = failedByRow.get(row) ?? [];
    const r = await resendFailed(fails, postReading);
    applyOutcome([row], { ...r, failed: [...r.failed, ...[...failedByRow].filter(([k]) => k !== row).flatMap(([, v]) => v)] });
  };

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    status.forEach((n) => n.replaceChildren());
    const rows: RowInput[] = [];
    for (const r of ENTRY_ROWS) {
      const v = readers.get(r)?.();
      if (v) rows.push(v);
    }
    if (rows.length === 0) { topErr.textContent = COPY["entry.noRows"]; return; }
    const r = await submitAll(rows, currentCrew(), seq, postReading);
    applyOutcome(rows.map((x) => x.ind === "bp" ? "bp" : x.ind), r);
  });
  root.append(form);
}
