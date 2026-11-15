// The signals screen (D45 §9.1): one card per signal, grouped. Read-only: the screen never writes to the hub.
import { ApiError, getPrompts, getSignals } from "../api";
import { COPY, DISCLAIMER } from "../copy";
import type { Ind, Prompt, Signal, SignalsBody } from "../contract";
import { CREW, currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { devLabel, estimateBadge, formatAge, srcLabel } from "../format";
import {
  GROUPS, groupOf, headline, lagLines, limitLines, missingLines, pairRows, pointCount, selfCheckFor, sparkValues,
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

/** The console's existing source chips: source, device label and age, plus the estimate badge where one applies. */
function chips(s: Signal, now: number): HTMLElement {
  const out = el("div", {});
  for (const i of s.inputs) {
    const age = formatAge(Math.max(0, (now - Date.parse(i.last_at)) / 1000));
    const replay = s.replay || i.src === "replay";
    out.append(el("span", { class: replay ? "chip replay" : "chip", text: `${srcLabel(i.src)} · ${devLabel(i.dev)} · ${age}` }));
    const badge = estimateBadge(i.ind as Ind, i.src, i.dev);
    if (badge) out.append(el("span", { class: "chip estimate", text: badge }));
  }
  return out;
}

/** Lagged pairs show their side-by-side table (§9.1). */
function pairsTable(s: Signal): HTMLElement | null {
  if (s.kind !== "lagged_pair" || !s.pairs.length) return null;
  const lagged = s.pairs.some((r) => r.length > 3);
  const heads = [
    COPY[lagged ? "signals.pairs.hour" : "signals.pairs.day"],
    COPY[`signals.pairs.x.${s.id}`] ?? COPY["signals.pairs.x"],
    COPY[`signals.pairs.y.${s.id}`] ?? COPY["signals.pairs.y"],
    ...(lagged ? [COPY["signals.pairs.lag"]] : []),
  ];
  return el("details", {},
    el("summary", { text: COPY["signals.pairs.title"].replace("{n}", String(s.pairs.length)) }),
    el("table", { class: "pairs" },
      el("thead", {}, el("tr", {}, ...heads.map((h) => el("th", { text: h })))),
      el("tbody", {}, ...pairRows(s).map((r) => el("tr", {}, ...r.map((c) => el("td", { text: c })))))));
}

export function signalCard(s: Signal, prompts: Prompt[], now: number): HTMLElement {
  const cls = s.state === "notable" ? "watch" : s.state === "steady" ? "ok" : "greyed";
  const how = el("details", {},
    el("summary", { text: COPY["signals.method"] }),
    el("div", { class: "footnote", text: `${s.method.name} · ${s.method.ref}` }),
    s.method.alpha !== null ? el("div", { class: "footnote", text: COPY["signals.alpha"].replace("{a}", String(s.method.alpha)) }) : null,
    el("div", { class: "footnote", text: COPY["signals.window"].replace("{n}", String(pointCount(s)))
      .replace("{from}", s.method.window_start.slice(0, 16)).replace("{to}", s.method.window_end.slice(0, 16)) }),
    ...limitLines(s).map((t) => el("div", { class: "footnote", text: t })),
  );
  const open = selfCheckFor(prompts, s);
  // Per-crew cards name their crew, and a replay card says so: replay and real are never shown as one.
  const who = [s.crew ? CREW.find((c) => c.id === s.crew)?.label ?? s.crew : null, s.replay ? COPY["src.replay"] : null]
    .filter((x): x is string => x !== null).join(" · ");
  return el("article", { class: `tile signal ${cls}`, "data-signal": s.id, "data-crew": s.crew ?? false },
    el("div", { class: "title", text: COPY[`signals.title.${s.id}`] ?? s.id }),
    who ? el("div", { class: s.replay ? "who age replay" : "who age", text: who }) : null,
    el("div", { class: "age", text: COPY[`signals.state.${s.state}`] }),
    el("p", { text: headline(s) }),
    ...missingLines(s).map((t) => el("p", { class: "footnote", text: t })),
    ...(s.id === "cabin_vs_earth" ? [...lagLines(s).map((t) => el("p", { class: "footnote", text: t })),
      el("p", { class: "footnote", text: COPY["signals.pair.noBest"] }),
      // Licence credit for the outdoor data (CC BY 4.0), plain text: the console is offline.
      el("p", { class: "footnote", text: COPY["signals.credit.weather"] })] : []),
    spark(sparkValues(s)),
    pairsTable(s),
    chips(s, now),
    open ? el("p", { class: "footnote", text: COPY["signals.selfCheck"] }) : null,
    how,
  );
}

/**
 * `body` null means the feature is off on the hub. `failed` adds the could-not-load line; with no body it is the
 * only line, so a failed request never reads as the feature being off.
 */
export function renderSignalsBody(root: HTMLElement, body: SignalsBody | null, prompts: Prompt[], now: number,
  failed = false): void {
  const note = failed ? el("p", { class: "footnote", text: COPY["signals.failed"] }) : null;
  if (!body) {
    root.replaceChildren(note ?? el("p", { text: COPY["signals.none"] }));
    return;
  }
  const sections = GROUPS.flatMap((g) => {
    const mine = body.signals.filter((s) => groupOf(s.id) === g);
    if (!mine.length) return [];
    return [el("section", {}, el("h2", { text: COPY[`signals.group.${g}`] }),
      el("div", { class: "grid" }, ...mine.map((s) => signalCard(s, prompts, now))))];
  });
  root.replaceChildren(...(note ? [note] : []), el("p", { text: COPY["signals.intro"] }), ...sections,
    el("p", { class: "footnote", text: DISCLAIMER }));
}

/** Only these mean the feature is off: a 503 signals_off, or a 404 when the hub has no signals routes. */
function signalsOff(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 404 || (e.status === 503 && e.message.includes("signals_off")));
}

export function renderSignals(root: HTMLElement): () => void {
  let disposed = false;
  let token = 0;
  let last: { body: SignalsBody; prompts: Prompt[] } | null = null;
  const load = async () => {
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const [res, prompts] = await Promise.all([
      getSignals(crew).then((body) => ({ body }), (err: unknown) => ({ err })),
      getPrompts(crew, "open").catch(() => [] as Prompt[]),
    ]);
    if (disposed || mine !== token) return;
    if ("body" in res) {
      last = { body: res.body, prompts };
      renderSignalsBody(root, res.body, prompts, Date.now());
    } else if (signalsOff(res.err)) {
      last = null;
      renderSignalsBody(root, null, [], Date.now());
    } else {
      // Keep the last cards that loaded, and say the refresh failed.
      renderSignalsBody(root, last?.body ?? null, last?.prompts ?? [], Date.now(), true);
    }
  };
  void load();
  const t = setInterval(() => void load(), REFRESH_MS);
  const off = onCrewChange(() => {
    last = null; // another crew's cards are never kept
    void load();
  });
  return () => {
    disposed = true;
    clearInterval(t);
    off();
  };
}
