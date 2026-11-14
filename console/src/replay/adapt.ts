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

function entryOf(p: Record<string, unknown>): StatusEntry {
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

// Newest reading per indicator among the arrivals at or before the position. Only `reading` items count.
export function statusAt(file: ReplayFile, positionMs: number, crew: CrewId | null): StatusBody {
  const latest = new Map<string, StatusEntry>();
  for (const a of file.arrivals) {
    if (a.at_ms > positionMs) break;
    for (const item of a.items) {
      if (item.kind !== "reading") continue;
      const e = entryOf(item.payload);
      if (!appliesToCrew(e, crew)) continue;
      const cur = latest.get(e.ind);
      if (!cur || Date.parse(e.measured_at) >= Date.parse(cur.measured_at)) latest.set(e.ind, e);
    }
  }
  return { crew, generated_at: new Date(Date.parse(file.t0) + positionMs).toISOString(), nodes: [], results: [...latest.values()] };
}

export function linkAt(file: ReplayFile, positionMs: number): LinkState | null {
  let link: LinkState | null = null;
  for (const a of file.arrivals) {
    if (a.at_ms > positionMs) break;
    if (a.beacon) link = a.beacon.link;
  }
  return link;
}
