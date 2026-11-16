import type { Alert, ExerciseDay, Ind, RepMessage, Session, StoredReading, StoredRep } from "../contract";
import { COPY } from "../copy";
import type { PanelSource } from "../views/panel/source";
import { countUpTo, linkAt, readingIndex, statusAt, type ReplayFile } from "./adapt";

// The habitat panel in the replay build. Like the status board, it shows the habitat side of the recording: each
// reading and alert at its measured time on the replay clock (t0 + position), so an alert's packet reaches Earth
// when the ground receiver recorded it. The link state comes from the beacons.

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

/** First and last measured time of the readings, in ms. */
export function recordedSpan(file: ReplayFile): [number, number] {
  const ts = [...readingIndex(file).values()].flatMap((rows) => [rows[0].t, rows[rows.length - 1].t]);
  if (!ts.length) return [Date.parse(file.t0), Date.parse(file.t0)];
  return [Math.min(...ts), Math.max(...ts)];
}

/** Readings of `ind` measured in [sinceMs, nowMs], oldest first. */
export function readingsUntil(file: ReplayFile, ind: Ind, sinceMs: number, nowMs: number): StoredReading[] {
  const rows = readingIndex(file).get(ind) ?? [];
  return rows.slice(countUpTo(rows, sinceMs, false), countUpTo(rows, nowMs)).map((r) => r.p as unknown as StoredReading);
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
    label: COPY["src.replay"],
    setNote: set ? COPY["panel.replaySet"] : undefined,
    // Replay wording where the live wording would point at a hub.
    text: {
      "panel.noData": COPY["replay.unavailable"],
      "panel.massNone": COPY["panel.massNoneReplay"],
      "panel.window": COPY["panel.windowReplay"],
      "panel.notOnBench": COPY["panel.notInReplay"],
    },
    now,
    refreshMs: 2000,
    lanesRefreshMs: 2000,
    laneWindow: () => [span[0] / 1000, span[1] / 1000],
    status: async () => statusAt(file, positionMs(), null),
    sessions: async () => (set && Date.parse(set.session.started_at) <= now() ? [set.session] : []),
    reps: async (id) => ({
      session: id,
      pairs: id === set?.session.session ? repsBy(now()).map((r) => ({ rep: r.rep, camera: r, load_cell: null, work_cell_j: null })) : [],
    }),
    readings: async (ind, o) => readingsUntil(file, ind, o?.since ? Date.parse(o.since) : -Infinity, now()),
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
