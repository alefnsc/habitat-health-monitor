import type { Alert, ExerciseDay, Ind, RepMessage, Session, StatusBody, StatusEntry, StoredReading, StoredRep } from "../contract";
import type { PanelSource } from "../views/panel/source";
import { entryOf, linkAt, type ReplayFile } from "./adapt";

// The habitat panel in the replay build. The panel shows the habitat side of the recording: each reading and alert
// at its measured time on the replay clock (t0 + position), so an alert's packet reaches Earth when the ground
// receiver recorded it. The link state comes from the beacons, as on the status board.

const DAY_MS = 86_400_000;

export interface ReplaySet {
  session: Session;
  reps: StoredRep[];
}

/** The exercise replay's reps as one camera session starting at `startMs`; each rep sits at start + its end time. */
export function parseExerciseReplay(text: string, startMs: number): ReplaySet | null {
  const msgs: RepMessage[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const o = JSON.parse(line) as { kind?: string; msg?: RepMessage };
      if (o.kind === "rep" && o.msg?.type === "rep") msgs.push(o.msg);
    } catch {
      /* not a replay line */
    }
  }
  const mine = msgs.filter((m) => m.session === msgs[0]?.session);
  if (!mine.length) return null;
  const reps: StoredRep[] = mine.map((m, i) => ({ ...m, id: i + 1, measured_at: new Date(startMs + m.t1_ms).toISOString() }));
  const first = reps[0];
  return {
    session: {
      session: first.session, mass_kg: first.mass_kg, g: first.g, crew: null,
      started_at: new Date(startMs).toISOString(), ended_at: reps[reps.length - 1].measured_at,
      camera_reps: reps.filter((r) => r.src === "camera").length,
      load_cell_reps: reps.filter((r) => r.src === "load_cell").length,
      exercise: first.exercise ?? null,
    },
    reps,
  };
}

type Timed = { t: number; r: StoredReading; p: Record<string, unknown> };
const cache = new WeakMap<ReplayFile, Timed[]>();

/** Every reading in the file, oldest measured first. */
function timed(file: ReplayFile): Timed[] {
  let rows = cache.get(file);
  if (!rows) {
    rows = file.arrivals.flatMap((a) => a.items.filter((i) => i.kind === "reading"))
      .map((i) => ({ t: Date.parse(i.payload.measured_at as string), r: i.payload as unknown as StoredReading, p: i.payload }))
      .filter((x) => Number.isFinite(x.t))
      .sort((a, b) => a.t - b.t);
    cache.set(file, rows);
  }
  return rows;
}

/** First and last measured time of the readings, in ms. */
export function recordedSpan(file: ReplayFile): [number, number] {
  const rows = timed(file);
  if (!rows.length) return [Date.parse(file.t0), Date.parse(file.t0)];
  return [rows[0].t, rows[rows.length - 1].t];
}

/** Readings of `ind` measured in [sinceMs, nowMs], oldest first. */
export function readingsUntil(file: ReplayFile, ind: Ind, sinceMs: number, nowMs: number): StoredReading[] {
  return timed(file).filter((x) => x.r.ind === ind && x.t >= sinceMs && x.t <= nowMs).map((x) => x.r);
}

/** The newest reading per indicator measured by `nowMs`. */
export function statusUntil(file: ReplayFile, nowMs: number): StatusBody {
  const latest = new Map<string, StatusEntry>();
  for (const x of timed(file)) {
    if (x.t > nowMs) break;
    latest.set(x.r.ind, entryOf(x.p));
  }
  return { crew: null, generated_at: new Date(nowMs).toISOString(), nodes: [], results: [...latest.values()] };
}

/** Alerts raised in (fromMs, toMs]: at their measured time, or at their arrival when the file has none. */
export function alertsBetween(file: ReplayFile, fromMs: number, toMs: number): Alert[] {
  const t0 = Date.parse(file.t0);
  const out: Alert[] = [];
  for (const a of file.arrivals) {
    for (const i of a.items) {
      if (i.kind !== "alert") continue;
      const m = Date.parse(i.payload.measured_at as string);
      const t = Number.isFinite(m) ? m : t0 + a.at_ms;
      if (t > fromMs && t <= toMs) out.push(i.payload as unknown as Alert);
    }
  }
  return out;
}

const notInReplay = (): Promise<never> => Promise.reject(new Error("not in the replay"));

/** The panel's data source in the replay build, at the player's position. */
export function replaySource(file: ReplayFile, set: ReplaySet | null, positionMs: () => number): PanelSource {
  const t0 = Date.parse(file.t0);
  const now = () => t0 + positionMs();
  const span = recordedSpan(file);
  const repsBy = (n: number) => (set?.reps ?? []).filter((r) => r.src === "camera" && Date.parse(r.measured_at) <= n);
  return {
    replay: true,
    now,
    refreshMs: 2000,
    lanesRefreshMs: 2000,
    laneWindow: () => [span[0] / 1000, span[1] / 1000],
    status: async () => statusUntil(file, now()),
    sessions: async () => (set && Date.parse(set.session.started_at) <= now() ? [set.session] : []),
    reps: async (id) => ({
      session: id,
      pairs: id === set?.session.session ? repsBy(now()).map((r) => ({ rep: r.rep, camera: r, load_cell: null, work_cell_j: null })) : [],
    }),
    readings: async (ind, o) => readingsUntil(file, ind, Date.parse(o.since), now()),
    foodDay: notInReplay,
    exerciseDay: async (): Promise<ExerciseDay> => {
      const n = now();
      const cams = repsBy(n).filter((r) => Date.parse(r.measured_at) > n - DAY_MS);
      return {
        window_start: new Date(n - DAY_MS).toISOString(), window_end: new Date(n).toISOString(),
        sessions: cams.length ? 1 : 0, camera_reps: cams.length,
        camera_work_j: cams.length ? cams.reduce((s, r) => s + r.work_j, 0) : null,
        cell_work_j: null, replay: true, excluded_reps: 0,
      };
    },
    spaceWeather: notInReplay,
    issCabin: notInReplay,
    issReference: notInReplay,
    link: async () => {
      const l = linkAt(file, positionMs());
      if (!l) throw new Error("no link beacon yet");
      return l;
    },
  };
}
