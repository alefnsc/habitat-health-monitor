import type { LinkState } from "../../contract";

/** How long one message takes on screen: the one-way light time at the demo time scale. */
export function holdMs(link: Pick<LinkState, "light_time_s" | "time_scale">): number {
  const scale = link.time_scale > 0 ? link.time_scale : 1;
  return (link.light_time_s / scale) * 1000;
}

/**
 * Position of each alert on the line, 0 at Mars and 1 at Earth, newest last. Alerts that already reached Earth
 * leave the line. In a blackout every alert still on the line waits at Mars.
 */
export function packetsInFlight(sentAtMs: number[], nowMs: number, hold: number, state: LinkState["state"]): number[] {
  const out: number[] = [];
  for (const t of [...sentAtMs].sort((a, b) => a - b)) {
    const x = hold > 0 ? (nowMs - t) / hold : 1;
    if (x < 0 || x > 1) continue;
    out.push(state === "blackout" ? 0 : x);
  }
  return out;
}

/** "12 min" or "45 s": a light time for prose. */
export function lightText(s: number): string {
  return s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`;
}
