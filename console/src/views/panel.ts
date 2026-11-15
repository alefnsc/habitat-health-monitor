import {
  getExerciseDay, getFoodDay, getIssCabin, getIssReference, getLink, getReadings, getReps, getSessions, getSpaceWeather,
  getStatus,
} from "../api";
import type { CrewId, RepsBody, Session, StoredReading } from "../contract";
import { currentCrew, onCrewChange } from "../crew";
import { el } from "../dom";
import { linkCard } from "./panel/link";
import { liftCard, placesCard } from "./panel/lift";
import { massCard } from "./panel/mass";
import { radiationCard } from "./panel/radiation";
import { topBar } from "./panel/topbar";
import { PANEL_LANES, vitalsCard } from "./panel/vitals";

// The habitat panel (D43): one frame in the video's reading order. Every card loads on its own; a failed request
// leaves that card at "No data" and the others alone. The panel only reads from the hub.
const REFRESH_MS = 10_000;
const LANE_HOURS = 6;
const LANE_LIMIT = 5000;
const MASS_DAYS = 30;

const soft = <T>(p: Promise<T>): Promise<T | null> => p.catch(() => null);

async function latestSet(crew: CrewId | undefined): Promise<{ sessions: Session[] | null; session: Session | null; reps: RepsBody | null }> {
  const sessions = await soft(getSessions());
  const mine = (sessions ?? []).filter((s) => crew === undefined || s.crew === crew);
  const session = mine[0] ?? null;
  const reps = session ? await soft(getReps(session.session)) : null;
  return { sessions: mine, session, reps };
}

async function laneRows(sinceIso: string, crew: CrewId | undefined): Promise<Record<string, StoredReading[]> | null> {
  const all = await Promise.all(PANEL_LANES.map((s) => soft(getReadings(s.ind!, { since: sinceIso, limit: LANE_LIMIT, crew }))));
  if (all.every((r) => r === null)) return null;
  return Object.fromEntries(PANEL_LANES.map((s, i) => [s.key, all[i] ?? []]));
}

export function renderPanel(root: HTMLElement): () => void {
  const top = topBar();
  const lift = liftCard();
  const places = placesCard();
  const mass = massCard();
  const vitals = vitalsCard();
  const link = linkCard();
  const rad = radiationCard();
  root.replaceChildren(el("div", { class: "panel" }, top.node, lift.node, places.node, mass.node, vitals.node, link.node, rad.node));

  let token = 0;
  let disposed = false;
  const load = async () => {
    const mine = ++token;
    const crew = currentCrew() ?? undefined;
    const nowS = Date.now() / 1000;
    const sinceS = nowS - LANE_HOURS * 3600;
    const [status, set, weather, linkState, weighIns, food, training, rows, iss, ref] = await Promise.all([
      soft(getStatus(crew)), latestSet(crew), soft(getSpaceWeather()), soft(getLink()),
      soft(getReadings("body_mass", { since: new Date((nowS - MASS_DAYS * 86400) * 1000).toISOString(), limit: 500, crew })),
      soft(getFoodDay(crew)), soft(getExerciseDay(crew)), laneRows(new Date(sinceS * 1000).toISOString(), crew),
      soft(getIssCabin()), soft(getIssReference()),
    ]);
    if (disposed || mine !== token) return;
    top.update({ status, sessions: set.sessions, weather, link: linkState });
    lift.update(set);
    places.update(set);
    mass.update({ weighIns, food, training, sessions: set.sessions });
    vitals.update({ rows, win: [sinceS, nowS], iss });
    rad.update({ ref, weather });
    link.update(linkState);
  };
  void load();
  const timer = setInterval(() => void load(), REFRESH_MS);
  const offCrew = onCrewChange(() => void load());
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
