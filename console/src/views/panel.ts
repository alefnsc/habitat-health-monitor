import type { CrewId, RepsBody, Session, StoredReading } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { laneCrew, pickSession } from "../model/panel/pick";
import { linkCard } from "./panel/link";
import { liftCard, placesCard } from "./panel/lift";
import { massCard } from "./panel/mass";
import { radiationCard } from "./panel/radiation";
import { liveSource, type PanelSource } from "./panel/source";
import { topBar } from "./panel/topbar";
import { PANEL_LANES, vitalsCard } from "./panel/vitals";

// The habitat panel (D43): one frame in the video's reading order. Every card loads on its own; a failed request
// leaves that card at "No data" and the others alone. The panel only reads from the hub.
const REFRESH_MS = 10_000;
const LANES_REFRESH_MS = 30_000; // the lane readings are the heavy request: refetch them less often
const SIGNALS_REFRESH_MS = 30_000; // D45 signals are worked out on read for every crew: on their own, slower cadence
export const LANE_HOURS = 6;
export const LANE_BUCKET_S = 60; // a few stored readings per minute, so a fast sensor cannot cut the window
export const LANE_LIMIT = 5000;
const MASS_DAYS = 30;

const soft = <T>(p: Promise<T>): Promise<T | null> => p.catch(() => null);

async function latestSet(src: PanelSource, crew: CrewId | undefined): Promise<{ sessions: Session[] | null; session: Session | null; reps: RepsBody | null }> {
  const sessions = await soft(src.sessions());
  // Camera sessions started without a crew still belong on every crew's panel.
  const mine = (sessions ?? []).filter((s) => crew === undefined || s.crew === crew || s.crew === null);
  const session = pickSession(mine);
  const reps = session ? await soft(src.reps(session.session)) : null;
  return { sessions: mine, session, reps };
}

async function laneRows(src: PanelSource, sinceIso: string, crew: CrewId | undefined): Promise<Record<string, StoredReading[]> | null> {
  const all = await Promise.all(PANEL_LANES.map((s) => soft(src.readings(s.ind!, {
    since: sinceIso, limit: LANE_LIMIT, crew: laneCrew(s.ind!, crew), bucket_s: LANE_BUCKET_S,
  }))));
  if (all.every((r) => r === null)) return null;
  return Object.fromEntries(PANEL_LANES.map((s, i) => [s.key, all[i] ?? []]));
}

/** The panel, read from the hub (`liveSource`) or from a recorded replay (`replaySource`), which can set its own clock. */
export function renderPanel(root: HTMLElement, src: PanelSource = liveSource): () => void {
  const top = topBar(src);
  const lift = liftCard(src);
  const places = placesCard(src);
  const mass = massCard(src);
  const vitals = vitalsCard(src);
  const link = linkCard();
  const rad = radiationCard(src);
  root.replaceChildren(el("div", { class: "panel" }, top.node, lift.node, places.node, mass.node, vitals.node, link.node, rad.node));

  let token = 0;
  let disposed = false;
  let lanesAt = 0;
  let signalsAt = 0;
  let signalsToken = 0;
  // The signals chip loads on its own: no card waits for the evaluation.
  const loadSignals = () => {
    if (!src.signals || Date.now() - signalsAt < SIGNALS_REFRESH_MS) return;
    signalsAt = Date.now();
    const mine = ++signalsToken;
    void soft(src.signals(currentCrew() ?? undefined)).then((b) => {
      if (!disposed && mine === signalsToken) top.signals(b);
    });
  };
  const load = async () => {
    loadSignals();
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const nowS = src.now() / 1000;
    const win = src.laneWindow?.(nowS) ?? [nowS - LANE_HOURS * 3600, nowS];
    const lanesDue = Date.now() - lanesAt >= (src.lanesRefreshMs ?? LANES_REFRESH_MS);
    const [status, set, weather, linkState, weighIns, food, training, rows, iss, ref] = await Promise.all([
      soft(src.status(crew)), latestSet(src, crew), soft(src.spaceWeather()), soft(src.link()),
      soft(src.readings("body_mass", { since: new Date((nowS - MASS_DAYS * 86400) * 1000).toISOString(), limit: 500, crew })),
      soft(src.foodDay(crew)), soft(src.exerciseDay(crew)),
      lanesDue ? laneRows(src, new Date(win[0] * 1000).toISOString(), crew) : Promise.resolve(undefined),
      soft(src.issCabin()), soft(src.issReference()),
    ]);
    if (disposed || mine !== token) return;
    top.update({ status, sessions: set.sessions, weather, link: linkState });
    lift.update(set);
    places.update(set);
    mass.update({ weighIns, food, training, sessions: set.sessions });
    if (rows !== undefined) {
      lanesAt = Date.now();
      vitals.update({ rows, win, iss, latest: status?.results ?? null });
    }
    rad.update({ ref, weather });
    link.update(linkState);
  };
  void load();
  const timer = setInterval(() => void load(), src.refreshMs ?? REFRESH_MS);
  const offCrew = onCrewChange(() => {
    lanesAt = 0;
    signalsAt = 0;
    void load();
  });
  return () => {
    disposed = true;
    clearInterval(timer);
    offCrew();
    top.dispose();
    mass.dispose();
    vitals.dispose();
    link.dispose();
  };
}
