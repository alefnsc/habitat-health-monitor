import "./style.css";
import { arrivalMs, emptyView, reduce } from "./model";
import { apiBase, replayUrl } from "./paths";
import { loadReplay, positionLabel, replayBanner, replaySource } from "./replay";
import type { GuidanceItem } from "./replay";
import { render, renderCrewView } from "./render";
import { decideMode, fetchSummary, liveBanner } from "./mode";
import { liveSource } from "./sources";
import type { GroundView } from "./types";
import { emptyLit, litSpots, noteArrival, spotsInFile } from "./habitat";
import { linkFrame, linkSchedule, liveLinkFrame } from "./linkview";
import { renderOverview } from "./overview";

const root = document.querySelector<HTMLDivElement>("#app")!;
const controls = document.querySelector<HTMLDivElement>("#controls")!;
const crew = document.querySelector<HTMLDivElement>("#crew")!;
const overview = document.querySelector<HTMLDivElement>("#overview")!;
const source = import.meta.env.VITE_GROUND_SOURCE === "replay" ? "replay" : "live";

let view: GroundView = emptyView();
let lit = emptyLit();

/** Redraw the overview every animation frame so packets move smoothly. */
function animate(frame: () => void): void {
  const loop = () => {
    frame();
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

function startLive(): void {
  const base = apiBase("live", import.meta.env.VITE_API_BASE as string | undefined);
  liveSource(
    base,
    (a) => {
      const now = Date.now();
      view = reduce(view, a, arrivalMs(a, now));
      lit = noteArrival(lit, a, now);
    },
    (...args) => fetch(...args),
  );
  const draw = () =>
    render(root, view, Date.now(), import.meta.env.VITE_GROUND_SOURCE === "auto" ? liveBanner(view) : null);
  draw();
  setInterval(draw, 500);
  animate(() => {
    const now = Date.now();
    renderOverview(overview, liveLinkFrame(view.beacon, view.lastArrivalMs, now), litSpots(lit, now), null);
  });
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
  const schedule = linkSchedule(file);
  const present = spotsInFile(file);
  const src = replaySource(
    file,
    (a) => {
      view = reduce(view, a, Date.parse(a.received_at));
      lit = noteArrival(lit, a, Date.parse(a.received_at));
    },
    () => {
      view = emptyView();
      lit = emptyLit();
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
  animate(() => {
    src.tick();
    const p = src.positionMs();
    renderOverview(overview, linkFrame(schedule, p), litSpots(lit, t0 + p), present);
  });
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
