import { framesOf, pickRecordedSide, type WristSample } from "../../vendor/ground-truth/demo/src/pose/landmarks";
import type { PoseFrame } from "@ground-truth/capture";
import { COPY } from "./copy";
import type { Exercise, RepMessage } from "./reps";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type CrewId = "crew-a" | "crew-b" | "crew-c";

// D5 and D4 shapes, same field names as the console contract.
export interface Session {
  session: string;
  mass_kg: number;
  g: number;
  crew: CrewId | null;
  started_at: string;
  ended_at: string | null;
  camera_reps: number;
  load_cell_reps: number;
  exercise: Exercise | null;
}

export interface PostResult {
  id: number;
  measured_at: string;
  duplicate: boolean;
  results: unknown[];
}

async function send<T>(path: string, body: unknown, fetchImpl: typeof fetch): Promise<T> {
  let res: Response;
  try {
    res = await fetchImpl(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new ApiError(0, e instanceof Error ? e.message : "network error");
  }
  let json: unknown = null;
  try {
    json = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const reason = json && typeof json === "object" && typeof (json as { reason?: unknown }).reason === "string" ? `: ${(json as { reason: string }).reason}` : "";
    throw new ApiError(res.status, `HTTP ${res.status}${reason}`);
  }
  return json as T;
}

// No `session` field: the hub generates s-<epoch_ms> (D5).
export const startSession = (body: { mass_kg: number; g: number; crew?: CrewId; exercise?: Exercise }, fetchImpl: typeof fetch = fetch): Promise<Session> =>
  send<Session>("/api/sessions", body, fetchImpl);

export const endSession = (session: string, fetchImpl: typeof fetch = fetch): Promise<Session> =>
  send<Session>(`/api/sessions/${encodeURIComponent(session)}/end`, undefined, fetchImpl);

export const postRep = (msg: RepMessage, fetchImpl: typeof fetch = fetch): Promise<PostResult> =>
  send<PostResult>("/api/reps", msg, fetchImpl);

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// Any 2xx counts as sent (a duplicate included). A 422 is shown and never retried. The hub dedupes on
// (node, boot, seq), so re-sending the same message is safe.
export async function postRepsWithRetry(
  msgs: RepMessage[],
  post: (m: RepMessage) => Promise<PostResult>,
  opts: { intervalMs: number; maxTries: number; onPending?: (n: number) => void; age?: (m: RepMessage) => number } = { intervalMs: 2000, maxTries: 15 },
): Promise<{ sent: number; pending: number; rejected: { seq: number; reason: string }[] }> {
  let sent = 0;
  let pending = 0;
  const rejected: { seq: number; reason: string }[] = [];
  for (const m of msgs) {
    let done = false;
    for (let attempt = 1; attempt <= opts.maxTries && !done; attempt++) {
      try {
        // age_ms is the rep's age at send time, so recompute it on every attempt.
        await post(opts.age ? { ...m, age_ms: opts.age(m) } : m);
        sent += 1;
        done = true;
      } catch (e) {
        const status = e instanceof ApiError ? e.status : 0;
        if (status >= 400 && status < 500) {
          rejected.push({ seq: m.seq, reason: e instanceof Error ? e.message : String(e) });
          done = true;
        } else {
          opts.onPending?.(pending + 1);
          if (attempt < opts.maxTries) await sleep(opts.intervalMs);
        }
      }
    }
    if (!done) pending += 1;
    opts.onPending?.(pending);
  }
  return { sent, pending, rejected };
}

// Held reps live in memory only, so a reload loses them: warn while any are pending.
export function unloadGuard(getPending: () => number): (e: { preventDefault(): void; returnValue?: unknown }) => void {
  return (e) => {
    if (getPending() > 0) {
      e.preventDefault();
      e.returnValue = COPY["set.unsent"];
    }
  };
}

export function framesForSet(samples: WristSample[]): { side: "LEFT" | "RIGHT"; frames: PoseFrame[] } {
  const side = pickRecordedSide(samples);
  return { side, frames: framesOf(samples, side) };
}
