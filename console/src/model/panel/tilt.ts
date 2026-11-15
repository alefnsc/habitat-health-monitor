import { COPY } from "../../copy";
import type { RepPair, TiltWitness } from "../../contract";

/** One line for the lift card from the hub's tilt witnesses, or null when no rep of the set has one. */
export function tiltLine(pairs: RepPair[]): string | null {
  const ws = pairs.map((p) => p.tilt).filter((t): t is TiltWitness => !!t);
  if (!ws.length) return null;
  const line = COPY["panel.tiltLine"]
    .replace("{seen}", String(ws.filter((t) => t.seen).length))
    .replace("{n}", String(ws.length))
    .replace("{inside}", String(ws.filter((t) => t.turn_inside).length));
  const offs = ws.filter((t) => t.seen && t.offset_ms !== null).map((t) => t.offset_ms as number).sort((a, b) => a - b);
  if (!offs.length) return line;
  const mid = offs.length / 2;
  const median = Math.round(offs.length % 2 ? offs[Math.floor(mid)] : (offs[mid - 1] + offs[mid]) / 2);
  return `${line} ${COPY["panel.tiltOffset"].replace("{ms}", `${median >= 0 ? "+" : "−"}${Math.abs(median)}`)}`;
}
