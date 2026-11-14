import { COPY } from "../copy";
import type { CrewId, Ind, StatusBody, StatusEntry } from "../contract";
import { RULES } from "./rules";
import { devLabel, estimateBadge, flagText, formatAge, formatValue, sourceKindLabel, srcLabel, statusClass, statusLabel } from "../format";

export interface TileSpec {
  id: string;
  title: string;
  inds: Ind[];
}

const spec = (id: string, inds: Ind[] = [id as Ind]): TileSpec => ({ id, title: COPY[`tile.${id}`], inds });

export const BOARD_LAYOUT: { vitals: TileSpec[]; supporting: TileSpec[]; cabin: TileSpec[] } = {
  vitals: [spec("bp", ["bp_sys", "bp_dia"]), spec("hr"), spec("glucose"), spec("body_temp"), spec("sleep_h"), spec("mood")],
  supporting: [spec("spo2"), spec("skin_temp")],
  cabin: [spec("cabin_ppco2"), spec("cabin_temp"), spec("cabin_rh"), spec("cabin_p"), spec("cabin_lux"), spec("cabin_co2")],
};

export type TileClass = "ok" | "watch" | "act" | "unknown" | "greyed";

export interface Tile {
  id: string;
  title: string;
  value: string;
  unit: string;
  statusClass: TileClass;
  statusLabel: string;
  srcLabel: string;
  sourceKindLabel: string;
  sourceRef: string | null;
  devText: string | null;
  badges: string[];
  flags: string[];
  ageText: string;
  ruleId: string | null;
  guidanceId: string | null;
  crewChip: string | null;
}

const RANK: Record<TileClass, number> = { ok: 0, unknown: 1, greyed: 2, watch: 3, act: 4 };
const CREW_LABEL: Record<CrewId, string> = { "crew-a": COPY["crew.a"], "crew-b": COPY["crew.b"], "crew-c": COPY["crew.c"] };

const cls = (e: StatusEntry) => statusClass(e.status, e.q);

function emptyTile(s: TileSpec, label: string): Tile {
  return {
    id: s.id, title: s.title, value: COPY["status.none"], unit: "", statusClass: "unknown", statusLabel: label,
    srcLabel: "", sourceKindLabel: "", sourceRef: null, devText: null, badges: [], flags: [], ageText: "",
    ruleId: null, guidanceId: null, crewChip: null,
  };
}

const WINDOW_WAIT: Record<string, string> = { mean_1h: "1-hour mean", mean_7d: "7-day mean", dose_24h: "24-hour dose", cumulative: "cumulative total" };

// A rule exists but the hub has no verdict yet (for example one reading and a 1-hour mean rule): say what it waits for.
function waitingLabel(e: StatusEntry): string | null {
  if (e.status !== "unknown" || !e.rule_id || e.q.some((f) => f !== "ok")) return null;
  const rule = RULES.find((r) => r.id === e.rule_id);
  const what = rule ? (WINDOW_WAIT[rule.window] ?? "more readings") : "more readings";
  const kind = e.source_kind ?? rule?.source_kind ?? null;
  const ref = e.source_ref ?? rule?.source_ref ?? "";
  const id = ref.match(/\[[^\]]+\]/)?.[0] ?? "";
  const cite = kind ? `${sourceKindLabel(kind)}${id ? ` ${id}` : ""}` : "";
  return `${COPY["status.waitingFor"]} ${what}${cite ? ` (${cite})` : ""}`;
}

function fromEntry(s: TileSpec, e: StatusEntry, nowMs: number, value: string): Tile {
  const badge = estimateBadge(e.ind, e.src, e.dev);
  return {
    id: s.id,
    title: s.title,
    value,
    unit: e.unit,
    statusClass: cls(e),
    statusLabel: waitingLabel(e) ?? statusLabel(e.status, e.q),
    srcLabel: srcLabel(e.src),
    sourceKindLabel: sourceKindLabel(e.source_kind ?? RULES.find((r) => r.id === e.rule_id)?.source_kind ?? null),
    sourceRef: e.source_kind === "nasa_std" || e.source_kind === "nasa_doc" ? e.source_ref : null,
    devText: devLabel(e.dev),
    badges: badge ? [badge] : [],
    flags: e.q.filter((f) => f !== "ok").map(flagText),
    ageText: formatAge((nowMs - Date.parse(e.measured_at)) / 1000),
    ruleId: e.rule_id,
    guidanceId: e.guidance_id,
    crewChip: e.crew ? CREW_LABEL[e.crew] : null,
  };
}

export function buildTiles(entries: StatusEntry[], nowMs: number): Tile[] {
  const byInd = new Map(entries.map((e) => [e.ind, e]));
  const all = [...BOARD_LAYOUT.vitals, ...BOARD_LAYOUT.supporting, ...BOARD_LAYOUT.cabin];
  return all.map((s): Tile => {
    if (s.id === "bp") {
      const sys = byInd.get("bp_sys");
      const dia = byInd.get("bp_dia");
      if (!sys && !dia) return emptyTile(s, COPY["status.noReading"]);
      const worse = !sys ? dia! : !dia ? sys : RANK[cls(sys)] >= RANK[cls(dia)] ? sys : dia;
      const f = (e?: StatusEntry) => (e ? formatValue(e.ind, e.val, "").trim() : COPY["status.none"]);
      const t = fromEntry(s, worse, nowMs, `${f(sys)}/${f(dia)} mmHg`);
      const both = [sys, dia].filter((e): e is StatusEntry => !!e);
      t.flags = [...new Set(both.flatMap((e) => e.q.filter((q) => q !== "ok").map(flagText)))];
      t.ageText = formatAge((nowMs - Math.min(...both.map((e) => Date.parse(e.measured_at)))) / 1000);
      if (!sys || !dia) {
        t.statusClass = "unknown";
        t.statusLabel = COPY["status.incomplete"];
      }
      return t;
    }
    const e = byInd.get(s.inds[0]);
    if (!e) return emptyTile(s, COPY["status.noReading"]);
    return fromEntry(s, e, nowMs, formatValue(e.ind, e.val, e.unit));
  });
}

export function applySnapshot(body: StatusBody): StatusEntry[] {
  return [...body.results];
}

export function applyAssessment(entries: StatusEntry[], e: StatusEntry): StatusEntry[] {
  const cur = entries.find((x) => x.ind === e.ind);
  if (cur && Date.parse(e.measured_at) < Date.parse(cur.measured_at)) return entries;
  return [...entries.filter((x) => x.ind !== e.ind), e];
}

// When one crew member is selected, frames for another crew member are ignored. Cabin frames have no crew.
export function appliesToCrew(e: StatusEntry, selected: CrewId | null): boolean {
  return selected === null || e.crew === null || e.crew === selected;
}
