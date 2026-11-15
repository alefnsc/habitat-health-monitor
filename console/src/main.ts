import "./styles.css";
import "uplot/dist/uPlot.min.css";
import { getPrompts } from "./api";
import { COPY } from "./copy";
import type { Prompt } from "./contract";
import { CREW, currentCrew, onCrewChange, setCurrentCrew } from "./crew";
import { el } from "./dom";
import { appliesToCrew, applySnapshot } from "./model/status";
import { board, hubEvents } from "./state";
import { SCREENS, screenFromHash, type Screen } from "./screens";
import { mountReplayApp } from "./replay/app";
import { renderEntry } from "./views/entry";
import { renderFood } from "./views/food";
import { renderExercise } from "./views/exercise";
import { renderHistory } from "./views/history";
import { renderLanes } from "./views/lanes";
import { renderPanel } from "./views/panel";
import { renderSignals } from "./views/signals";
import { entryForTile, openGuidance, setLinkState } from "./views/guidance";
import { refreshBanner, renderNasa, startBanner } from "./views/nasa";
import { loadBoard, renderStatus } from "./views/status";
import { connectWs, wsUrl } from "./ws";

export { SCREENS, screenFromHash, type Screen };

const HUB_LOST_AFTER_MS = 5000;

export function mountApp(root: HTMLElement): void {
  if (import.meta.env.MODE === "replay") {
    void mountReplayApp(root, { base: import.meta.env.BASE_URL, fetchImpl: (u) => fetch(u) });
    return;
  }
  const lost = el("div", { class: "hub-lost", role: "alert", hidden: true, text: COPY["app.hubLost"] });
  const nav = el("nav", { class: "nav", "aria-label": "Screens" });
  const crewSel = el("select", { id: "crew-select" });
  crewSel.append(el("option", { value: "", text: COPY["crew.all"] }));
  for (const c of CREW) crewSel.append(el("option", { value: c.id, text: c.label }));
  crewSel.value = currentCrew() ?? "";
  crewSel.addEventListener("change", () => setCurrentCrew((crewSel.value || null) as ReturnType<typeof currentCrew>));
  const bannerBox = el("div", { id: "sw-banner" });
  const title = el("h1", { class: "screen-title" });
  const screen = el("section", { id: "screen" });
  const mainEl = el("main", {}, title, screen, el("p", { class: "footnote", text: COPY["app.disclaimer"] }));
  root.replaceChildren(
    el("div", { class: "banner", text: COPY["app.banner"] }),
    lost,
    bannerBox,
    el(
      "header",
      { class: "top" },
      nav,
      el("div", {}, el("label", { for: "crew-select", text: `${COPY["crew.viewing"]} ` }), crewSel),
    ),
    mainEl,
  );

  const badge = el("span", { class: "badge-count", hidden: true });
  const buttons = new Map<Screen, HTMLButtonElement>();
  for (const s of SCREENS) {
    const b = el("button", { type: "button", text: COPY[`nav.${s}`] });
    if (s === "prompts") b.append(badge);
    b.addEventListener("click", () => {
      location.hash = `#/${s}`;
    });
    buttons.set(s, b);
    nav.append(b);
  }

  startBanner(bannerBox);
  onCrewChange(() => void refreshBanner());
  let dispose: (() => void) | null = null;
  const render = () => {
    const cur = screenFromHash(location.hash);
    title.textContent = COPY[`nav.${cur}`];
    buttons.forEach((b, s) => (s === cur ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
    dispose?.();
    dispose = null;
    screen.replaceChildren();
    mainEl.classList.toggle("wide", cur === "panel");
    title.hidden = cur === "panel"; // the active nav button already names it; the panel needs the height
    if (cur === "panel") dispose = renderPanel(screen);
    else if (cur === "status") dispose = renderStatus(screen, (t) => {
      const toHistory = () => {
        location.hash = `#/history/${t.id === "bp" ? "bp_sys" : t.id}`;
      };
      const e = entryForTile(t.id);
      if (e) void openGuidance(e, toHistory);
      else toHistory();
    });
    else if (cur === "entry") renderEntry(screen);
    else if (cur === "history") dispose = renderHistory(screen);
    else if (cur === "lanes") dispose = renderLanes(screen);
    else if (cur === "exercise") dispose = renderExercise(screen);
    else if (cur === "nasa") dispose = renderNasa(screen);
    else if (cur === "food") dispose = renderFood(screen);
    else if (cur === "signals") dispose = renderSignals(screen);
    else screen.append(el("p", { text: COPY["screen.pending"] }));
  };
  window.addEventListener("hashchange", render);
  render();

  // Live data: one WebSocket for the whole app.
  const openPrompts = new Map<number, Prompt>();
  const showPromptCount = () => {
    badge.textContent = String(openPrompts.size);
    badge.hidden = openPrompts.size === 0;
  };
  const loadPrompts = async () => {
    try {
      const list = await getPrompts(currentCrew() ?? undefined);
      openPrompts.clear();
      list.forEach((p) => openPrompts.set(p.id, p));
      showPromptCount();
    } catch {
      /* hub offline: banner covers it */
    }
  };
  const ws = connectWs(wsUrl(), (m) => {
    if (m.type === "snapshot") {
      board.replace(applySnapshot(m.data).filter((e) => appliesToCrew(e, currentCrew())));
      void loadPrompts();
    } else if (m.type === "assessment") {
      if (m.data.ind === "space_weather") void refreshBanner();
      if (appliesToCrew(m.data, currentCrew())) board.apply([m.data]);
    } else if (m.type === "link") {
      setLinkState(m.data);
      hubEvents.link(m.data);
    } else if (m.type === "alert") {
      hubEvents.alert(m.data);
      // On the panel the alert is drawn in place (amber lane, packet on the link), so the popup does not cover it.
      if ((m.data.status === "watch" || m.data.status === "act") && screenFromHash(location.hash) !== "panel") {
        const e = board.entries.find((x) => x.ind === m.data.ind);
        if (e) void openGuidance(e);
      }
      if (m.data.rule_id === "radiation_spe") void refreshBanner();
    } else if (m.type === "prompt") {
      if (m.data.status === "open") openPrompts.set(m.data.id, m.data);
      else openPrompts.delete(m.data.id);
      showPromptCount();
    }
  });
  onCrewChange(() => {
    crewSel.value = currentCrew() ?? "";
    void loadBoard();
    void loadPrompts();
  });

  let downSince: number | null = null;
  setInterval(() => {
    if (ws.state() === "open") downSince = null;
    else downSince ??= Date.now();
    lost.hidden = downSince === null || Date.now() - downSince <= HUB_LOST_AFTER_MS;
  }, 1000);
}

const appRoot = typeof document !== "undefined" ? document.getElementById("app") : null;
if (appRoot) mountApp(appRoot);
