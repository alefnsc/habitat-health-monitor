// The signals screen (D45 §9.1): one card per signal, grouped. Read-only: the screen never writes to the hub.
import { getPrompts, getSignals } from "../api";
import { COPY, DISCLAIMER } from "../copy";
import type { Prompt, Signal, SignalsBody } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { formatAge, srcLabel } from "../format";
import {
  GROUPS, groupOf, headline, lagLines, limitLines, missingLines, selfCheckFor, sparkValues,
} from "../model/signals";

const REFRESH_MS = 30_000;
/** A sparkline drawn from markup, as the panel's link strip is (numbers only go into it). */
function spark(values: number[]): HTMLElement | null {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * 100).toFixed(1)},${(28 - ((v - lo) / span) * 24).toFixed(1)}`);
  const box = el("div", { class: "spark", "aria-hidden": "true" });
  box.innerHTML = `<svg viewBox="0 0 100 30" preserveAspectRatio="none"><polyline points="${pts.join(" ")}"/></svg>`;
  return box;
}

function chips(s: Signal, now: number): HTMLElement {
  const out = el("div", {});
  for (const i of s.inputs) {
    const age = formatAge(Math.max(0, (now - Date.parse(i.last_at)) / 1000));
    out.append(el("span", { class: s.replay ? "chip estimate" : "chip", text: `${srcLabel(i.src)} · ${i.dev} · ${age}` }));
  }
  return out;
}

export function signalCard(s: Signal, prompts: Prompt[], now: number): HTMLElement {
  const cls = s.state === "notable" ? "watch" : s.state === "steady" ? "ok" : "greyed";
  const how = el("details", {},
    el("summary", { text: COPY["signals.method"] }),
    el("div", { class: "footnote", text: `${s.method.name} · ${s.method.ref}` }),
    el("div", { class: "footnote", text: COPY["signals.window"].replace("{n}", String(s.method.n))
      .replace("{from}", s.method.window_start.slice(0, 16)).replace("{to}", s.method.window_end.slice(0, 16)) }),
    ...limitLines(s).map((t) => el("div", { class: "footnote", text: t })),
  );
  const open = selfCheckFor(prompts, s);
  return el("article", { class: `tile signal ${cls}`, "data-signal": s.id },
    el("div", { class: "title", text: COPY[`signals.title.${s.id}`] ?? s.id }),
    el("div", { class: "age", text: COPY[`signals.state.${s.state}`] }),
    el("p", { text: headline(s) }),
    ...missingLines(s).map((t) => el("p", { class: "footnote", text: t })),
    ...(s.id === "cabin_vs_earth" ? [...lagLines(s).map((t) => el("p", { class: "footnote", text: t })),
      el("p", { class: "footnote", text: COPY["signals.pair.noBest"] }),
      // Licence credit for the outdoor data (CC BY 4.0), plain text: the console is offline.
      el("p", { class: "footnote", text: COPY["signals.credit.weather"] })] : []),
    spark(sparkValues(s)),
    chips(s, now),
    open ? el("p", { class: "footnote", text: COPY["signals.selfCheck"] }) : null,
    how,
  );
}

export function renderSignalsBody(root: HTMLElement, body: SignalsBody | null, prompts: Prompt[], now: number): void {
  if (!body) {
    root.replaceChildren(el("p", { text: COPY["signals.none"] }));
    return;
  }
  const sections = GROUPS.flatMap((g) => {
    const mine = body.signals.filter((s) => groupOf(s.id) === g);
    if (!mine.length) return [];
    return [el("section", {}, el("h2", { text: COPY[`signals.group.${g}`] }),
      el("div", { class: "grid" }, ...mine.map((s) => signalCard(s, prompts, now))))];
  });
  root.replaceChildren(el("p", { text: COPY["signals.intro"] }), ...sections, el("p", { class: "footnote", text: DISCLAIMER }));
}

export function renderSignals(root: HTMLElement): () => void {
  let disposed = false;
  let token = 0;
  const load = async () => {
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const [body, prompts] = await Promise.all([
      getSignals(crew).catch(() => null),
      getPrompts(crew, "open").catch(() => [] as Prompt[]),
    ]);
    if (disposed || mine !== token) return;
    renderSignalsBody(root, body, prompts, Date.now());
  };
  void load();
  const t = setInterval(() => void load(), REFRESH_MS);
  const off = onCrewChange(() => void load());
  return () => {
    disposed = true;
    clearInterval(t);
    off();
  };
}
