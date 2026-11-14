import "./style.css";
import { emptyView, reduce } from "./model";
import { apiBase, replayUrl } from "./paths";
import { loadReplay, positionLabel, replayBanner, replaySource } from "./replay";
import type { GuidanceItem } from "./replay";
import { render, renderCrewView } from "./render";
import { LIVE_BANNER, decideMode, fetchSummary } from "./mode";
import { liveSource } from "./sources";
import type { GroundView } from "./types";

const root = document.querySelector<HTMLDivElement>("#app")!;
const controls = document.querySelector<HTMLDivElement>("#controls")!;
const crew = document.querySelector<HTMLDivElement>("#crew")!;
const source = import.meta.env.VITE_GROUND_SOURCE === "replay" ? "replay" : "live";

let view: GroundView = emptyView();

function startLive(): void {
  const base = apiBase("live", import.meta.env.VITE_API_BASE as string | undefined);
  liveSource(
    base,
    (a) => {
      view = reduce(view, a, Date.now());
    },
    (...args) => fetch(...args),
  );
  const draw = () =>
    render(root, view, Date.now(), import.meta.env.VITE_GROUND_SOURCE === "auto" ? LIVE_BANNER : null);
  draw();
  setInterval(draw, 500);
}

async function loadGuidance(): Promise<GuidanceItem[] | null> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}guidance.json`);
    return res.ok ? ((await res.json()) as GuidanceItem[]) : null;
  } catch {
    return null;
  }
}

async function startReplay(): Promise<void> {
  const loaded = await loadReplay(replayUrl(import.meta.env.BASE_URL), (...a) => fetch(...a));
  if ("message" in loaded) {
    root.textContent = loaded.message;
    return;
  }
  const file = loaded.file;
  const t0 = Date.parse(file.t0);
  const guidance = await loadGuidance();
  const src = replaySource(
    file,
    (a) => {
      view = reduce(view, a, Date.parse(a.received_at));
    },
    () => {
      view = emptyView();
    },
    () => performance.now(),
  );
  controls.innerHTML = `<button id="pp" type="button">Pause</button>
    <button id="rs" type="button">Restart</button> <span id="pos"></span>`;
  let paused = false;
  const pp = controls.querySelector<HTMLButtonElement>("#pp")!;
  pp.onclick = () => {
    paused = !paused;
    if (paused) src.pause();
    else src.play();
    pp.textContent = paused ? "Play" : "Pause";
  };
  controls.querySelector<HTMLButtonElement>("#rs")!.onclick = () => src.restart();
  const pos = controls.querySelector<HTMLSpanElement>("#pos")!;

  const banner = replayBanner(file.label);
  const draw = () => {
    src.tick();
    render(root, view, t0 + src.positionMs(), banner);
    renderCrewView(crew, view, guidance);
    pos.textContent = positionLabel(src.positionMs(), src.durationMs());
  };
  draw();
  setInterval(draw, 250);
}

const mode = import.meta.env.VITE_GROUND_SOURCE;
if (mode === "auto") {
  void (async () => {
    const current = decideMode(await fetchSummary("", (...a) => fetch(...a)), Date.now());
    if (current === "live") startLive();
    else await startReplay();
    setInterval(async () => {
      const next = decideMode(await fetchSummary("", (...a) => fetch(...a)), Date.now());
      if (next !== current) location.reload();
    }, 60_000);
  })();
} else if (source === "replay") {
  void startReplay();
} else {
  startLive();
}
