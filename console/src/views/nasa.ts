import { ApiError, ackSpaceWeather, getIssCabin, getIssReference, getSpaceWeather } from "../api";
import { COPY } from "../copy";
import type { IssCabin, IssReference, SpaceWeather } from "../contract";
import { currentCrew } from "../crew";
import { el } from "../dom";
import { ackState, doseBar, issVsHabitat, weatherBanner } from "../model/nasa";
import { board } from "../state";

// ---- banner: shown at the top of every screen ----

let bannerHost: HTMLElement | null = null;
let lastWeather: SpaceWeather | null = null;

function drawBanner() {
  if (!bannerHost) return;
  const host = bannerHost;
  host.replaceChildren();
  if (!lastWeather) return;
  const b = weatherBanner(lastWeather, Date.now());
  if (!b.show) return;
  const box = el("div", { class: `sw-banner tile ${b.cls}`, role: "alert" }, el("strong", { text: b.title }), el("div", { text: b.detail }));
  if (b.link) box.append(el("a", { href: b.link, target: "_blank", rel: "noopener", text: "DONKI record" }));
  if (b.ackText) {
    const state = ackState(lastWeather, currentCrew());
    const btn = el("button", { type: "button", text: COPY["nasa.ack"] });
    if (!state.enabled) btn.setAttribute("disabled", "");
    const err = el("span", { class: "err" });
    btn.addEventListener("click", async () => {
      const crew = currentCrew();
      if (!crew) return;
      try {
        await ackSpaceWeather(crew);
        await refreshBanner();
      } catch (e) {
        err.textContent = e instanceof ApiError && e.status === 409 ? COPY["nasa.noActive"] : e instanceof Error ? e.message : String(e);
      }
    });
    box.append(el("div", {}, el("span", { text: b.ackText }), " ", btn, state.hint ? el("span", { class: "footnote", text: ` ${state.hint}` }) : null, err));
  }
  host.append(box);
}

export async function refreshBanner(): Promise<void> {
  try {
    lastWeather = await getSpaceWeather();
  } catch {
    lastWeather = null; // 404 (feature off) or 503: no banner
  }
  drawBanner();
}

export function startBanner(host: HTMLElement): void {
  bannerHost = host;
  void refreshBanner();
  setInterval(() => void refreshBanner(), 60_000);
}

// ---- NASA panel ----

export function renderNasa(root: HTMLElement): () => void {
  let disposed = false;
  const host = el("div");
  root.replaceChildren(host);
  let iss: IssCabin | null = null;
  let ref: IssReference | null = null;

  const draw = () => {
    if (disposed) return;
    host.replaceChildren();
    if (!iss && !ref && !lastWeather) {
      host.append(el("p", { class: "tile greyed", text: COPY["nasa.unavailable"] }));
      return;
    }
    host.append(el("h2", { text: COPY["nasa.issTitle"] }));
    const cmp = issVsHabitat(iss, ref, board.entries, Date.now());
    const table = el("table", {}, el("tr", {}, ...["", "Habitat now", "ISS Live", "ISS reference (OSDR)", "NASA limit"].map((t) => el("th", { text: t }))));
    for (const r of cmp.rows) {
      table.append(el("tr", {}, el("td", { text: r.label }), el("td", { text: r.habitat }), el("td", { text: r.issLive }, " ", el("span", { class: "chip", text: r.issLiveAge })), el("td", { text: r.issRef }), el("td", { text: r.limit })));
    }
    host.append(table);
    if (ref) host.append(el("p", { class: "footnote", text: `OSDR snapshot ${ref.snapshot_date}` }));
    for (const f of cmp.footnote) host.append(el("p", { class: "footnote", text: f }));
    if (ref) {
      const d = doseBar(ref.dose);
      host.append(el("h2", { text: COPY["nasa.career"] }), el("p", { text: d.effectiveText }));
      if (d.showBar) {
        const bar = el("div", { class: `dose-bar ${d.statusCls}`, style: "position:relative;height:18px;background:#26313d;border-radius:4px" });
        bar.append(el("div", { style: `width:${d.pct}%;height:100%;background:var(--${d.statusCls === "ok" ? "ok" : d.statusCls});border-radius:4px` }));
        for (const m of d.markers) bar.append(el("div", { title: m.label, style: `position:absolute;left:${m.pct}%;top:0;bottom:0;border-left:2px solid #e6ebf0` }));
        host.append(bar, ...d.markers.map((m) => el("div", { class: "footnote", text: m.label })));
      }
      host.append(el("p", { text: d.absorbedText }), el("p", { class: "footnote", text: d.profileText }));
      if (d.basisText) host.append(el("p", { class: "footnote", text: d.basisText }));
      host.append(el("p", { class: "footnote", text: COPY["nasa.speNote"] }));
    }
  };

  const load = async () => {
    await refreshBanner();
    [iss, ref] = await Promise.all([getIssCabin().catch(() => null), getIssReference().catch(() => null)]);
    draw();
  };
  void load();
  const t = setInterval(() => void load(), 10_000);
  return () => { disposed = true; clearInterval(t); };
}
