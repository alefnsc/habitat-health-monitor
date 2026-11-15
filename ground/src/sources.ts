import type { Arrival } from "./types";

const POLL_MS = 1000;
/** Arrivals per request. The server also cuts a page at a byte budget; paging carries on either way. */
export const PAGE = 250;
const BACKOFF_MIN_MS = 1000;
const BACKOFF_MAX_MS = 30_000;

/** Poll the receiver, paging until an empty page, then wait one poll interval.
 * On errors wait 1 s, doubling up to 30 s, until a request succeeds. */
export function liveSource(
  apiBase: string,
  onArrival: (a: Arrival) => void,
  fetchFn: typeof fetch,
): { stop(): void } {
  let after = 0;
  let stopped = false;
  let backoff = BACKOFF_MIN_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const later = (ms: number) => {
    if (!stopped) timer = setTimeout(tick, ms);
  };

  async function tick(): Promise<void> {
    if (stopped) return;
    try {
      const res = await fetchFn(`${apiBase}/ground/arrivals?after=${after}&limit=${PAGE}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const page = (await res.json()) as Arrival[];
      backoff = BACKOFF_MIN_MS;
      if (page.length === 0) return later(POLL_MS);
      for (const a of page) {
        onArrival(a);
        after = a.arrival_id;
      }
      void tick();
    } catch {
      later(backoff);
      backoff = Math.min(backoff * 2, BACKOFF_MAX_MS);
    }
  }

  void tick();
  return {
    stop() {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}
