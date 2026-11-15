import "../styles.css";
import { COPY } from "../copy";
import { el } from "../dom";
import { screenFromHash, SCREENS } from "../screens";
import { board } from "../state";
import { entryForTile, openGuidance, setLinkState } from "../views/guidance";
import { renderStatus } from "../views/status";
import { parseReplayFile } from "./adapt";
import { createReplayPlayer, replayBanner } from "./player";

// Replay mode: one fetch of replay.json from the build base, no API call, no WebSocket.
export async function mountReplayApp(root: HTMLElement, o: { base: string; fetchImpl: (url: string) => Promise<Response> }): Promise<void> {
  const banner = el("div", { class: "banner", text: COPY["app.banner"] });
  const replayBar = el("div", { class: "banner", role: "status" });
  const nav = el("nav", { class: "nav", "aria-label": "Screens" });
  const title = el("h1", { class: "screen-title" });
  const screen = el("section", { id: "screen" });
  const controls = el("div");
  root.replaceChildren(banner, replayBar, el("header", { class: "top" }, nav), el("main", {}, title, controls, screen, el("p", { class: "footnote", text: COPY["app.disclaimer"] })));

  let file;
  try {
    const res = await o.fetchImpl(`${o.base}replay.json`);
    if (!res.ok) throw new Error("Replay file not recognised");
    file = parseReplayFile(await res.json());
  } catch {
    root.replaceChildren(el("p", { text: COPY["replay.notRecognised"] }));
    return;
  }

  const buttons = new Map<string, HTMLButtonElement>();
  for (const s of SCREENS.filter((x) => x !== "panel")) { // the panel needs a live hub
    const b = el("button", { type: "button", text: COPY[`nav.${s}`] });
    b.addEventListener("click", () => { location.hash = `#/${s}`; });
    buttons.set(s, b);
    nav.append(b);
  }
  let dispose: (() => void) | null = null;
  const render = () => {
    const cur = screenFromHash(location.hash, "status");
    title.textContent = COPY[`nav.${cur}`];
    buttons.forEach((b, s) => (s === cur ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
    dispose?.();
    dispose = null;
    screen.replaceChildren();
    if (cur === "status") {
      dispose = renderStatus(screen, (t) => {
        const e = entryForTile(t.id);
        if (e) void openGuidance(e);
      }, false);
    } else {
      screen.append(el("p", { text: COPY["replay.unavailable"] }));
    }
  };
  window.addEventListener("hashchange", render);

  const player = createReplayPlayer(file, () => Date.now(), (f) => {
    replayBar.textContent = replayBanner(file.label, f.positionMs, player.durationMs());
    if (f.link) setLinkState(f.link);
    board.replace(f.status.results);
  });
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
