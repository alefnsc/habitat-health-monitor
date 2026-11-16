import type { Ind, StatusEntry } from "../../contract";

/** The newest status entry for an indicator (any crew the board holds), or null. Used when a lane's window is empty. */
export function latestEntry(entries: StatusEntry[] | null | undefined, ind: Ind): StatusEntry | null {
  let best: StatusEntry | null = null;
  for (const e of entries ?? []) {
    if (e.ind !== ind) continue;
    if (!best || Date.parse(e.measured_at) > Date.parse(best.measured_at)) best = e;
  }
  return best;
}
