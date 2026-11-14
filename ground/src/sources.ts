import type { Arrival } from "./types";

const POLL_MS = 1000;
const PAGE = 1000;

/** Poll the receiver, paging until an empty page, then wait one poll interval. */
export function liveSource(
  apiBase: string,
  onArrival: (a: Arrival) => void,
  fetchFn: typeof fetch,
): { stop(): void } {
  let after = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const later = () => {
    if (!stopped) timer = setTimeout(tick, POLL_MS);
  };

  async function tick(): Promise<void> {
    if (stopped) return;
    try {
      const res = await fetchFn(`${apiBase}/ground/arrivals?after=${after}&limit=${PAGE}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const page = (await res.json()) as Arrival[];
      if (page.length === 0) return later();
      for (const a of page) {
        onArrival(a);
        after = a.arrival_id;
      }
      void tick();
    } catch {
      later();
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
