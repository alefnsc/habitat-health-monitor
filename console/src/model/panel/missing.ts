import type { Ind } from "../../contract";
import { COPY } from "../../copy";

// Which source would fill an empty lane on this bench.
const FILLER: Partial<Record<Ind, "ring" | "cabinNode" | "manual">> = {
  hr: "ring", spo2: "ring", sleep_h: "ring",
  cabin_ppco2: "cabinNode", cabin_p: "cabinNode", cabin_temp: "cabinNode", cabin_rh: "cabinNode",
};

/** "Not on this bench: heart rate, SpO2, sleep (ring import); …", or null when nothing is missing. */
export function missingLine(empty: Ind[], lead: string = COPY["panel.notOnBench"]): string | null {
  const groups = new Map<string, string[]>();
  for (const ind of empty) {
    const f = FILLER[ind] ?? "manual";
    groups.set(f, [...(groups.get(f) ?? []), COPY[`panel.short.${ind}`] ?? ind]);
  }
  if (!groups.size) return null;
  const parts = [...groups].map(([f, names]) => `${names.join(", ")} (${COPY[`panel.fill.${f}`]})`);
  return `${lead} ${parts.join("; ")}.`;
}
