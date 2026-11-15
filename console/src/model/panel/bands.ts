import type { Ind } from "../../contract";
import { COPY } from "../../copy";
import { sourceKindLabel } from "../../format";
import type { Band, ThresholdRule } from "../history";

const UNIT: Partial<Record<Ind, string>> = { cabin_temp: "°C", cabin_rh: "%" };

const range = (b: Band | null | undefined): [number, number] | null =>
  b && typeof b.min === "number" && typeof b.max === "number" ? [b.min, b.max] : null;

/**
 * One sentence that names both NASA-STD-3001 cabin bands for a value: the comfort (performance) zone, outside of
 * which the status is "watch", and the health limit, outside of which it is "act". Null for other indicators.
 */
export function bandSentence(rules: ThresholdRule[], ind: Ind, val: number): string | null {
  const unit = UNIT[ind];
  const mine = rules.filter((r) => r.ind === ind && r.window === "instant" && r.source_kind === "nasa_std");
  const zone = mine.find((r) => r.watch && !r.act);
  const box = mine.find((r) => r.act && !r.watch);
  const z = range(zone?.ok);
  const b = range(box?.ok);
  if (!unit || !z || !b || !Number.isFinite(val)) return null;
  const fmt = ([lo, hi]: [number, number]) => `${lo}–${hi} ${unit}`;
  const fill = (key: string, dir = "") =>
    COPY[key].replace("{zone}", fmt(z)).replace("{box}", fmt(b)).replace("{dir}", dir);
  if (val < b[0] || val > b[1]) return fill("panel.bandAct");
  if (val < z[0]) return fill("panel.bandWatch", COPY["panel.below"]);
  if (val > z[1]) return fill("panel.bandWatch", COPY["panel.above"]);
  return fill("panel.bandOk");
}

/** Short source for a lane: "NASA-STD-3001 [V2 6012] [V2 6013]", one kind label and every requirement ID once. */
export function compactSource(rules: ThresholdRule[]): string {
  if (!rules.length) return COPY["kind.none"];
  const groups = new Map<string, string[]>();
  for (const r of rules) {
    const kind = sourceKindLabel(r.source_kind);
    const ids = groups.get(kind) ?? [];
    for (const id of r.source_ref.match(/\[[^\]]+\]/g) ?? []) if (!ids.includes(id)) ids.push(id);
    groups.set(kind, ids);
  }
  return [...groups].map(([kind, ids]) => (ids.length ? `${kind} ${ids.join(" ")}` : kind)).join(" · ");
}
