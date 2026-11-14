import type { Tracker } from "../../vendor/ground-truth/demo/src/pose/source";
import type { PageState } from "./main";
import { COPY } from "./copy";
import { createRecorder, recordingProblem } from "./pose";
import { ENVIRONMENT_MENU, analyseRecording, inputProblemText, resultView, toRepMessages } from "./reps";
import { createSequencer } from "./seq";
import { createSetState } from "./set";
import { endSession, framesForSet, postRep, postRepsWithRetry, startSession, unloadGuard, type CrewId } from "./session";

function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...kids: (Node | string)[]): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "text" ? (n.textContent = v) : n.setAttribute(k, v);
  n.append(...kids);
  return n;
}

export function mountSet(host: HTMLElement, page: PageState): void {
  const setState = createSetState();
  const seq = createSequencer(Math.floor(Date.now() / 1000));
  let pendingReps = 0;
  window.addEventListener("beforeunload", unloadGuard(() => pendingReps));
  page.onScale((m) => setState.setScale(m));

  const crew = h("select", { id: "crew" });
  for (const [id, label] of [["crew-a", "Crew A"], ["crew-b", "Crew B"], ["crew-c", "Crew C"]]) crew.append(h("option", { value: id, text: label }));
  const mass = h("input", { id: "mass", type: "number", min: "0.1", max: "500", step: "0.1", value: "10" });
  const env = h("select", { id: "env" });
  for (const e of ENVIRONMENT_MENU) env.append(h("option", { value: String(e.g), text: e.label }));
  const start = h("button", { type: "button", text: "Start set" });
  const stop = h("button", { type: "button", text: "Stop set", disabled: "" });
  const sessionOut = h("p", { id: "session-id", style: "font-size:1.6rem" });
  const msg = h("p", { role: "status" });
  const results = h("div", { id: "results" });
  const sendOut = h("p", { id: "send-out" });
  if (recordingProblem(page.video)) {
    start.setAttribute("disabled", "");
    msg.textContent = recordingProblem(page.video) ?? "";
  }

  let recorder = createRecorder();
  let tracker: Tracker | null = null;
  let sessionId: string | null = null;
  let g = 9.81;
  let massKg = 10;

  start.addEventListener("click", async () => {
    msg.textContent = "";
    const ns = setState.nextSet();
    g = Number(env.value);
    massKg = Number(mass.value);
    const problem = inputProblemText({ massKg, gEnvMs2: g, deviceForceN: 0, metersPerUnit: ns.metersPerUnit });
    if (ns.needsCalibration) { msg.textContent = "Calibrate the scale first."; return; }
    if (problem) { msg.textContent = problem; return; }
    try {
      const s = await startSession({ mass_kg: massKg, g, crew: crew.value as CrewId });
      sessionId = s.session;
      sessionOut.textContent = s.session;
    } catch (e) {
      msg.textContent = e instanceof Error ? e.message : String(e);
      return;
    }
    recorder = createRecorder();
    tracker = page.record((s) => recorder.push(s), (e) => (msg.textContent = String(e)));
    start.setAttribute("disabled", "");
    stop.removeAttribute("disabled");
  });

  stop.addEventListener("click", async () => {
    tracker?.stop();
    stop.setAttribute("disabled", "");
    start.removeAttribute("disabled");
    if (!sessionId) return;
    const id = sessionId;
    void endSession(id).catch(() => {});
    const { frames } = framesForSet(recorder.samples);
    const inputs = { massKg, gEnvMs2: g, deviceForceN: 0, metersPerUnit: setState.nextSet().metersPerUnit };
    const problem = inputProblemText(inputs);
    results.replaceChildren();
    if (problem) { msg.textContent = problem; return; }
    const outcome = analyseRecording(frames, inputs, { id, title: "Camera set" });
    const view = resultView(outcome);
    if (view.rows.length) {
      const table = h("table", {}, h("tr", {}, ...["Rep", COPY["result.peak"], COPY["result.work"], COPY["result.workEcc"], COPY["result.tCon"], COPY["result.tEcc"], COPY["result.rom"], ""].map((t) => h("th", { text: t }))));
      for (const r of view.rows) {
        table.append(h("tr", {}, h("td", { text: String(r.rep) }), h("td", { text: r.peakN.toFixed(1) }), h("td", { text: r.workJ.toFixed(1) }), h("td", { text: r.eccJ.toFixed(1) }), h("td", { text: r.tConS.toFixed(2) }), h("td", { text: r.tEccS.toFixed(2) }), h("td", { text: r.romM.toFixed(2) }), h("td", {}, h("span", { text: r.badge }), ...r.notes.map((n) => h("div", { text: n })))));
      }
      results.append(table);
    }
    if (view.grade) results.append(h("p", { text: `${COPY["result.grade"]}: ${view.grade}` }));
    for (const n of view.notes) results.append(h("p", { text: n }));
    if (outcome.kind === "analysed") {
      const anchor = recorder.firstFramePerfMs ?? performance.now();
      const msgs = toRepMessages({ ok: true, reps: outcome.reps.map((r) => r.rep) }, {
        session: id, g, mass_kg: massKg, boot: seq.boot, seq, firstFramePerfMs: anchor, nowPerfMs: performance.now(),
      });
      sendOut.textContent = `${COPY["set.sent"]} 0 of ${msgs.length}`;
      const r = await postRepsWithRetry(msgs, (m) => postRep(m), {
        intervalMs: 2000, maxTries: 15,
        age: (m) => Math.max(0, Math.round(performance.now() - (anchor + m.t1_ms))),
        onPending: (n) => { pendingReps = n; sendOut.textContent = `${COPY["set.sent"]} ${msgs.length - n} of ${msgs.length}, ${n} waiting`; },
      });
      pendingReps = r.pending;
      sendOut.textContent = `${COPY["set.sent"]} ${r.sent} of ${msgs.length}, ${r.pending} waiting` + r.rejected.map((x) => `; rep ${x.seq}: ${x.reason}`).join("");
    }
    page.resumePreview();
  });

  host.replaceChildren(
    h("h2", { text: "Set" }),
    h("div", {}, h("label", { for: "crew", text: "Crew " }), crew, " ", h("label", { for: "mass", text: "Mass (kg) " }), mass, " ", h("label", { for: "env", text: "Environment " }), env),
    h("p", { text: COPY["env.note"] }),
    h("div", {}, start, " ", stop),
    sessionOut, msg, results, sendOut,
  );
}
