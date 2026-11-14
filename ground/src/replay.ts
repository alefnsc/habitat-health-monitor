import type { Arrival, ReplayFile } from "./types";

const LOOP_GAP_MS = 3000;
const DASH = "—";

export interface GuidanceItem {
  id: string;
  rule_id?: string;
  status?: string;
  do_now?: string;
  tell?: string;
  escalate_to?: string;
}

export function parseReplay(json: unknown): ReplayFile {
  const f = json as Partial<ReplayFile> | null;
  if (
    !f || typeof f !== "object" || f.kind !== "ground-replay" || f.v !== 1 ||
    !Array.isArray(f.arrivals) || typeof f.t0 !== "string" || typeof f.label !== "string"
  ) {
    throw new Error("not a ground replay file");
  }
  return f as ReplayFile;
}

export type LoadResult = { file: ReplayFile } | { message: string };

/** Fetch and parse the replay file; never throws. */
export async function loadReplay(url: string, fetchFn: typeof fetch): Promise<LoadResult> {
  let res: Response;
  try {
    res = await fetchFn(url);
  } catch {
    return { message: "Replay data not yet published" };
  }
  if (!res.ok) return { message: "Replay data not yet published" };
  try {
    return { file: parseReplay(await res.json()) };
  } catch {
    return { message: "Replay file not recognised" };
  }
}

export function replayBanner(label: string): string {
  return `Replay of a recorded session ${DASH} not live data. ${label}`;
}

function mmss(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function positionLabel(posMs: number, durMs: number): string {
  return `${mmss(posMs)} / ${mmss(durMs)}`;
}

export interface ReplaySource {
  play(): void;
  pause(): void;
  restart(): void;
  tick(): void;
  positionMs(): number;
  durationMs(): number;
}

/**
 * Plays a replay file on a caller-supplied clock. Call tick() often (the page
 * uses a 100 ms timer). Loops forever with a short gap after the last arrival.
 */
export function replaySource(
  file: ReplayFile,
  onArrival: (a: Arrival) => void,
  onReset: () => void,
  clock: () => number,
): ReplaySource {
  const t0 = Date.parse(file.t0);
  const duration = file.arrivals.reduce((m, a) => Math.max(m, a.at_ms), 0);
  const cycle = duration + LOOP_GAP_MS;
  let playing = true;
  let base = 0; // playback position at `since`
  let since = clock();
  let next = 0;

  const raw = () => (playing ? base + (clock() - since) : base);

  function seek(pos: number): void {
    base = pos;
    since = clock();
  }

  return {
    play() {
      if (playing) return;
      playing = true;
      since = clock();
    },
    pause() {
      if (!playing) return;
      base = raw();
      playing = false;
    },
    restart() {
      seek(0);
      next = 0;
      onReset();
    },
    tick() {
      let pos = raw();
      if (pos >= cycle) {
        pos %= cycle;
        seek(pos);
        next = 0;
        onReset();
      }
      while (next < file.arrivals.length && file.arrivals[next].at_ms <= pos) {
        const a = file.arrivals[next];
        next += 1;
        onArrival({
          arrival_id: next,
          received_at: new Date(t0 + a.at_ms).toISOString(),
          beacon: a.beacon,
          items: a.items,
        });
      }
    },
    positionMs: () => Math.min(raw(), duration),
    durationMs: () => duration,
  };
}
