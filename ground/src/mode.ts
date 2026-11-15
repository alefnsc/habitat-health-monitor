import { showsSynthetic } from "./model";
import type { GroundView } from "./types";

export const STALE_MS = 5 * 60 * 1000;
export const LIVE_BANNER = "Live from the habitat link, as received on Earth.";
export const SYNTHETIC_NOTE = "Readings from node sim-1 are synthetic.";

/** Live banner; it names sim-1 as synthetic only while such readings are on the page. */
export function liveBanner(view: GroundView): string {
  return showsSynthetic(view) ? `${LIVE_BANNER} ${SYNTHETIC_NOTE}` : LIVE_BANNER;
}

export interface SummaryLike {
  last_arrival_at: string | null;
}

export function decideMode(s: SummaryLike | null, nowMs: number): "live" | "replay" {
  if (!s || !s.last_arrival_at) return "replay";
  const t = Date.parse(s.last_arrival_at);
  if (Number.isNaN(t)) return "replay";
  return nowMs - t <= STALE_MS ? "live" : "replay";
}

export async function fetchSummary(
  apiBase: string,
  fetchFn: typeof fetch,
): Promise<SummaryLike | null> {
  try {
    const res = await fetchFn(`${apiBase}/ground/summary`);
    if (!res.ok) return null;
    return (await res.json()) as SummaryLike;
  } catch {
    return null;
  }
}
