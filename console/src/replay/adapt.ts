import type { CrewId, LinkState, SrcClass, StatusBody, StatusEntry } from "../contract";
import { appliesToCrew } from "../model/status";

interface OutboxItem {
  id: number;
  kind: "reading" | "rep" | "alert" | "prompt_answer";
  created_at: string;
  payload: Record<string, unknown>;
}

export interface ReplayFile {
  v: number;
  kind: "ground-replay";
  label: string;
  exported_at: string;
  t0: string;
  light_time_s: number;
  time_scale: number;
  arrivals: { at_ms: number; beacon: { link: LinkState } | null; items: OutboxItem[] }[];
}

export function parseReplayFile(json: unknown): ReplayFile {
  const o = json as Partial<ReplayFile> | null;
  if (!o || typeof o !== "object" || o.kind !== "ground-replay" || o.v !== 1 || !Array.isArray(o.arrivals)) {
    throw new Error("Replay file not recognised");
  }
  return o as ReplayFile;
}

export function entryOf(p: Record<string, unknown>): StatusEntry {
  const ruleId = (p.rule_id as string | null) ?? null;
  const status = p.status as StatusEntry["status"];
  return {
    ind: p.ind as StatusEntry["ind"],
    val: p.val as number,
    unit: p.unit as string,
    status,
    rule_id: ruleId,
    source_kind: (p.source_kind as StatusEntry["source_kind"]) ?? null,
    source_ref: null,
    guidance_id: ruleId ? `${ruleId}.${status}` : null,
    escalate_to: (p.escalate_to as StatusEntry["escalate_to"]) ?? "self",
    measured_at: p.measured_at as string,
    crew: (p.crew as CrewId | null) ?? null,
    src: p.src as SrcClass,
    dev: p.dev as string,
    q: (p.q as StatusEntry["q"]) ?? ["ok"],
    node: p.node as string,
    reading_id: p.id as number,
  };
}

export interface ReadingRow {
  t: number; // measured time, ms
  p: Record<string, unknown>;
}

const indexes = new WeakMap<ReplayFile, Map<string, ReadingRow[]>>();

/** The file's readings per indicator, oldest measured first. Built once per file. */
export function readingIndex(file: ReplayFile): Map<string, ReadingRow[]> {
  let byInd = indexes.get(file);
  if (!byInd) {
    byInd = new Map();
    for (const a of file.arrivals) {
      for (const item of a.items) {
        const t = Date.parse(item.payload.measured_at as string);
        if (item.kind !== "reading" || !Number.isFinite(t)) continue;
        const ind = item.payload.ind as string;
        const rows = byInd.get(ind) ?? [];
        if (!rows.length) byInd.set(ind, rows);
        rows.push({ t, p: item.payload });
      }
    }
    for (const rows of byInd.values()) rows.sort((x, y) => x.t - y.t); // stable: equal times keep arrival order
    indexes.set(file, byInd);
  }
  return byInd;
}

/** How many rows are measured at or before `x` (or strictly before it), by binary search. */
export function countUpTo(rows: readonly ReadingRow[], x: number, inclusive = true): number {
  let lo = 0;
  let hi = rows.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (inclusive ? rows[mid].t <= x : rows[mid].t < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

// Newest reading per indicator measured by the replay clock (t0 + position): the habitat side of the recording.
// The status board and the panel both read it, so they agree at every position. Only `reading` items count.
export function statusAt(file: ReplayFile, positionMs: number, crew: CrewId | null): StatusBody {
  const nowMs = Date.parse(file.t0) + positionMs;
  const results: StatusEntry[] = [];
  for (const rows of readingIndex(file).values()) {
    for (let i = countUpTo(rows, nowMs) - 1; i >= 0; i--) {
      const e = entryOf(rows[i].p);
      if (appliesToCrew(e, crew)) {
        results.push(e);
        break;
      }
    }
  }
  return { crew, generated_at: new Date(nowMs).toISOString(), nodes: [], results };
}

export function linkAt(file: ReplayFile, positionMs: number): LinkState | null {
  let link: LinkState | null = null;
  for (const a of file.arrivals) {
    if (a.at_ms > positionMs) break;
    if (a.beacon) link = a.beacon.link;
  }
  return link;
}
