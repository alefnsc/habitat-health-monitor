import type { LinkState } from "../../contract";

/** How long one message takes on screen: the one-way light time at the demo time scale. */
export function holdMs(link: Pick<LinkState, "light_time_s" | "time_scale">): number {
  const scale = link.time_scale > 0 ? link.time_scale : 1;
  return (link.light_time_s / scale) * 1000;
}

/** One alert on the Mars-to-Earth line. `startMs` is when it left Mars; null while it waits there. */
export interface Packet {
  sentMs: number;
  startMs: number | null;
}

const MAX_PACKETS = 50;

/** Record an alert: it leaves Mars at once when the link is in contact; otherwise it waits at Mars. */
export function queueAlert(packets: Packet[], nowMs: number, state: LinkState["state"]): Packet[] {
  return [...packets, { sentMs: nowMs, startMs: state === "contact" ? nowMs : null }].slice(-MAX_PACKETS);
}

/** When the link is (back) in contact, every alert still waiting at Mars leaves now, as the link simulator sends its queue. */
export function resume(packets: Packet[], nowMs: number, state: LinkState["state"]): Packet[] {
  if (state !== "contact") return packets;
  return packets.map((p) => (p.startMs === null ? { ...p, startMs: nowMs } : p));
}

/**
 * Where the alerts are: `moving` holds 0..1 positions (0 at Mars, 1 at Earth), oldest first; alerts already sent keep
 * moving through a blackout. `waiting` counts the alerts still queued at Mars.
 */
export function positions(packets: Packet[], nowMs: number, hold: number): { moving: number[]; waiting: number } {
  const moving: number[] = [];
  let waiting = 0;
  for (const p of [...packets].sort((a, b) => (a.startMs ?? Infinity) - (b.startMs ?? Infinity))) {
    if (p.startMs === null) {
      waiting++;
      continue;
    }
    const x = hold > 0 ? (nowMs - p.startMs) / hold : 1;
    if (x >= 0 && x <= 1) moving.push(x);
  }
  return { moving, waiting };
}

/** Drop alerts that already reached Earth; waiting alerts stay until the link sends them. */
export function prune(packets: Packet[], nowMs: number, hold: number): Packet[] {
  return packets.filter((p) => p.startMs === null || nowMs - p.startMs <= hold);
}

/** "12 min" or "45 s": a light time for prose. */
export function lightText(s: number): string {
  return s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`;
}
