import type { Beacon, BlackoutCause, ReplayFile } from "./types";

const BIG_ITEMS = 100;
const SILENCE_MS = 3000;

/** A span when the link is down at Mars, in replay time (ms after the file's t0). */
export interface Blackout {
  startMs: number;
  endMs: number;
  cause: BlackoutCause | null;
}

/** What the simulated link carries over a whole replay file. */
export interface LinkSchedule {
  holdMs: number;
  lightTimeS: number;
  timeScale: number;
  due: { atMs: number; items: number }[];
  blackouts: Blackout[];
}

/** One packet on the line: x runs from 0 at Mars to 1 at Earth. */
export interface Packet {
  x: number;
  big: boolean;
}

export interface LinkFrame {
  lightTimeMin: number | null;
  holdS: number | null;
  timeScale: number | null;
  packets: Packet[];
  /** Part of the line carrying signal from a blackout, as [from, to] in 0..1, or null. */
  gap: [number, number] | null;
  marsDown: boolean;
  earthDark: boolean;
  cause: BlackoutCause | null;
}

export function linkSchedule(file: ReplayFile): LinkSchedule {
  const t0 = Date.parse(file.t0);
  const first = file.arrivals.find((a) => a.beacon)?.beacon ?? null;
  const lightTimeS = first?.link.light_time_s ?? file.light_time_s;
  const timeScale = first?.link.time_scale ?? file.time_scale;
  const holdMs = (first?.hold_s ?? lightTimeS / timeScale) * 1000;

  const byStart = new Map<number, Blackout>();
  for (const a of file.arrivals) {
    const last = a.beacon?.link.last_blackout;
    if (!last) continue;
    const startMs = Date.parse(last.start) - t0;
    const endMs = last.end === null ? Infinity : Date.parse(last.end) - t0;
    const prev = byStart.get(startMs);
    if (!prev || endMs < prev.endMs) {
      byStart.set(startMs, { startMs, endMs, cause: a.beacon!.last_blackout_cause });
    }
  }

  return {
    holdMs,
    lightTimeS,
    timeScale,
    due: file.arrivals.map((a) => ({ atMs: a.at_ms, items: a.items.length })).sort((x, y) => x.atMs - y.atMs),
    blackouts: [...byStart.values()].sort((x, y) => x.startMs - y.startMs),
  };
}

/** The link at replay position `posMs`: what is in flight and where any blackout signal sits. */
export function linkFrame(s: LinkSchedule, posMs: number): LinkFrame {
  const h = s.holdMs;
  const packets = s.due
    .filter((d) => d.atMs > posMs && d.atMs <= posMs + h)
    .map((d) => ({ x: 1 - (d.atMs - posMs) / h, big: d.items > BIG_ITEMS }));

  // A signal at x left Mars at posMs - x*h; it is blackout signal when that falls in a blackout.
  let gap: [number, number] | null = null;
  let cause: BlackoutCause | null = null;
  for (const b of s.blackouts) {
    const lo = Math.max(0, (posMs - b.endMs) / h);
    const hi = Math.min(1, (posMs - b.startMs) / h);
    if (hi > 0 && lo < 1) {
      gap = [lo, hi];
      cause = b.cause;
      break;
    }
  }

  const within = (from: number, to: number) => posMs >= from && posMs < to;
  return {
    lightTimeMin: s.lightTimeS / 60,
    holdS: h / 1000,
    timeScale: s.timeScale,
    packets,
    gap,
    marsDown: s.blackouts.some((b) => within(b.startMs, b.endMs)),
    earthDark: s.blackouts.some((b) => within(b.startMs + h, b.endMs + h)),
    cause,
  };
}

/** Live mode has no schedule: light-time from the last beacon, Earth dark after a silence. */
export function liveLinkFrame(beacon: Beacon | null, lastArrivalMs: number | null, nowMs: number): LinkFrame {
  return {
    lightTimeMin: beacon ? beacon.link.light_time_s / 60 : null,
    holdS: beacon ? beacon.hold_s : null,
    timeScale: beacon ? beacon.link.time_scale : null,
    packets: [],
    gap: null,
    marsDown: false,
    earthDark: lastArrivalMs !== null && nowMs - lastArrivalMs > SILENCE_MS,
    cause: null,
  };
}
