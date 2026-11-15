import "../styles.css";
import { COPY } from "../copy";
import { el } from "../dom";
import { screenFromHash, SCREENS } from "../screens";
import { board, hubEvents } from "../state";
import { entryForTile, openGuidance, setLinkState } from "../views/guidance";
import { renderPanel } from "../views/panel";
import { renderStatus } from "../views/status";
import { parseReplayFile } from "./adapt";
import { alertsBetween, parseExerciseReplay, recordedSpan, replaySource } from "./panel";
import { createReplayPlayer, replayBanner } from "./player";

// The exercise replay is a separate synthetic recording: its set is shown this long before the cabin recording.
const SET_LEAD_MS = 60_000;

// Replay mode: replay.json and the exercise replay from the build base, no API call, no WebSocket. It opens on the
// habitat panel, fed by those two files; the status board stays in the navigation.
export async function mountReplayApp(root: HTMLElement, o: { base: string; fetchImpl: (url: string) => Promise<Response> }): Promise<void> {
  const banner = el("div", { class: "banner", text: COPY["app.banner"] });
  const replayBar = el("div", { class: "banner", role: "status" });
  const nav = el("nav", { class: "nav", "aria-label": "Screens" });
  const title = el("h1", { class: "screen-title" });
  const screen = el("section", { id: "screen" });
  const controls = el("div");
  const mainEl = el("main", {}, title, controls, screen, el("p", { class: "footnote", text: COPY["app.disclaimer"] }));
  root.replaceChildren(banner, replayBar, el("header", { class: "top" }, nav), mainEl);

  let file;
  try {
    const res = await o.fetchImpl(`${o.base}replay.json`);
    if (!res.ok) throw new Error("Replay file not recognised");
    file = parseReplayFile(await res.json());
  } catch {
    root.replaceChildren(el("p", { text: COPY["replay.notRecognised"] }));
    return;
  }
  // Optional: without it the lift cards keep their empty text.
  const exerciseText = await o.fetchImpl(`${o.base}exercise-day.jsonl`).then((r) => (r.ok ? r.text() : "")).catch(() => "");

  const buttons = new Map<string, HTMLButtonElement>();
  for (const s of SCREENS) {
    const b = el("button", { type: "button", text: COPY[`nav.${s}`] });
    b.addEventListener("click", () => { location.hash = `#/${s}`; });
    buttons.set(s, b);
    nav.append(b);
  }
  let dispose: (() => void) | null = null;
  const render = () => {
    const cur = screenFromHash(location.hash, "panel");
    title.textContent = COPY[`nav.${cur}`];
    buttons.forEach((b, s) => (s === cur ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
    dispose?.();
    dispose = null;
    screen.replaceChildren();
    mainEl.classList.toggle("wide", cur === "panel");
    title.hidden = cur === "panel"; // as in the console: the active nav button already names it
    if (cur === "panel") {
      dispose = renderPanel(screen, source);
    } else if (cur === "status") {
      dispose = renderStatus(screen, (t) => {
        const e = entryForTile(t.id);
        if (e) void openGuidance(e);
      }, false);
    } else {
      screen.append(el("p", { text: COPY["replay.unavailable"] }));
    }
  };
  window.addEventListener("hashchange", render);

  // Alerts go to the panel's link card at their measured time; a loop or a restart starts the count again.
  const t0 = Date.parse(file.t0);
  let alertsTo = -Infinity;
  let lastLink = "";
  const player = createReplayPlayer(file, () => Date.now(), (f) => {
    replayBar.textContent = replayBanner(file.label, f.positionMs, player.durationMs());
    if (f.link) {
      setLinkState(f.link);
      const key = JSON.stringify(f.link);
      if (key !== lastLink) hubEvents.link(f.link);
      lastLink = key;
    }
    board.replace(f.status.results);
    const nowMs = t0 + f.positionMs;
    if (nowMs < alertsTo) alertsTo = -Infinity;
    for (const a of alertsBetween(file, alertsTo, nowMs)) hubEvents.alert(a);
    alertsTo = nowMs;
  });
  const set = parseExerciseReplay(exerciseText, recordedSpan(file)[0] - SET_LEAD_MS);
  const source = replaySource(file, set, () => player.positionMs());
  const play = el("button", { type: "button", text: COPY["replay.pause"] });
  let playing = true;
  play.addEventListener("click", () => {
    playing = !playing;
    if (playing) player.play(); else player.pause();
    play.textContent = playing ? COPY["replay.pause"] : COPY["replay.play"];
  });
  const restart = el("button", { type: "button", text: COPY["replay.restart"] });
  restart.addEventListener("click", () => player.restart());
  controls.append(play, " ", restart);
  render();
  player.play();
}
