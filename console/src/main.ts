import "./styles.css";
import "uplot/dist/uPlot.min.css";
import { getPrompts } from "./api";
import { COPY } from "./copy";
import type { Prompt } from "./contract";
import { CREW, currentCrew, onCrewChange, setCurrentCrew } from "./crew";
import { el } from "./dom";
import { appliesToCrew, applySnapshot } from "./model/status";
import { board } from "./state";
import { renderEntry } from "./views/entry";
import { loadBoard, renderStatus } from "./views/status";
import { connectWs, wsUrl } from "./ws";

export const SCREENS = ["status", "entry", "history", "exercise", "nasa", "prompts", "body"] as const;
export type Screen = (typeof SCREENS)[number];

export function screenFromHash(hash: string): Screen {
  const name = hash.replace(/^#\/?/, "").split("/")[0];
  return (SCREENS as readonly string[]).includes(name) ? (name as Screen) : "status";
}

const HUB_LOST_AFTER_MS = 5000;

export function mountApp(root: HTMLElement): void {
  const lost = el("div", { class: "hub-lost", role: "alert", hidden: true, text: COPY["app.hubLost"] });
  const nav = el("nav", { class: "nav", "aria-label": "Screens" });
  const crewSel = el("select", { id: "crew-select" });
  crewSel.append(el("option", { value: "", text: COPY["crew.all"] }));
  for (const c of CREW) crewSel.append(el("option", { value: c.id, text: c.label }));
  crewSel.value = currentCrew() ?? "";
  crewSel.addEventListener("change", () => setCurrentCrew((crewSel.value || null) as ReturnType<typeof currentCrew>));
  const title = el("h1", { class: "screen-title" });
  const screen = el("section", { id: "screen" });
  root.replaceChildren(
    el("div", { class: "banner", text: COPY["app.banner"] }),
    lost,
    el(
      "header",
      { class: "top" },
      nav,
      el("div", {}, el("label", { for: "crew-select", text: `${COPY["crew.viewing"]} ` }), crewSel),
    ),
    el("main", {}, title, screen, el("p", { class: "footnote", text: COPY["app.disclaimer"] })),
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

  let dispose: (() => void) | null = null;
  const render = () => {
    const cur = screenFromHash(location.hash);
    title.textContent = COPY[`nav.${cur}`];
    buttons.forEach((b, s) => (s === cur ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
    dispose?.();
    dispose = null;
    screen.replaceChildren();
    if (cur === "status") dispose = renderStatus(screen);
    else if (cur === "entry") renderEntry(screen);
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
      if (appliesToCrew(m.data, currentCrew())) board.apply([m.data]);
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
