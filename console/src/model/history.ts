import type { Ind, SourceKind, StoredReading } from "../contract";

export interface Band {
  min?: number;
  max?: number;
  lt?: number;
  gt?: number;
}

export interface ThresholdRule {
  id: string;
  ind: Ind;
  window: "instant" | "mean_1h" | "mean_7d" | "dose_24h" | "cumulative";
  ok?: Band | null;
  watch?: Band | null;
  act?: Band | null;
  source_kind: SourceKind;
  source_ref: string;
  url: string;
  note: string;
}

const WINDOW_LABEL: Record<ThresholdRule["window"], string> = {
  instant: "instant",
  mean_1h: "1-hour mean",
  mean_7d: "7-day mean",
  dose_24h: "24-hour dose",
  cumulative: "cumulative",
};

export function toSeries(readings: StoredReading[]): { x: number[]; assessed: (number | null)[]; greyed: (number | null)[] } {
  const sorted = [...readings].sort((a, b) => Date.parse(a.measured_at) - Date.parse(b.measured_at));
  const x: number[] = [];
  const assessed: (number | null)[] = [];
  const greyed: (number | null)[] = [];
  for (const r of sorted) {
    x.push(Date.parse(r.measured_at) / 1000);
    const flagged = r.q.some((f) => f !== "ok");
    assessed.push(flagged ? null : r.val);
    greyed.push(flagged ? r.val : null);
  }
  return { x, assessed, greyed };
}

export function thresholdLines(
  rules: ThresholdRule[],
  ind: Ind,
): { lines: { y: number; label: string }[]; skipped: string[] } {
  const lines: { y: number; label: string }[] = [];
  const skipped: string[] = [];
  for (const rule of rules) {
    if (rule.ind !== ind) continue;
    const label = `${rule.id} (${WINDOW_LABEL[rule.window] ?? rule.window})`;
    const seen = new Set<number>();
    for (const band of [rule.ok, rule.watch, rule.act]) {
      if (!band) continue;
      for (const key of ["min", "max", "lt", "gt"] as const) {
        const y = band[key];
        if (typeof y === "number" && !seen.has(y)) {
          seen.add(y);
          lines.push({ y, label });
        }
      }
    }
    if (seen.size === 0) skipped.push(rule.id);
  }
  return { lines, skipped };
}

export function defaultWindow(ind: Ind): { sinceIsoOffsetH: number; limit: number } {
  if (ind.startsWith("cabin_")) return { sinceIsoOffsetH: 6, limit: 5000 };
  if (ind === "sleep_h" || ind === "mood") return { sinceIsoOffsetH: 30 * 24, limit: 60 };
  return { sinceIsoOffsetH: 7 * 24, limit: 2000 };
}

const DAY = 86400;
const dayStart = (iso: string) => Math.floor(Date.parse(iso) / 1000 / DAY) * DAY;

function perDay(readings: StoredReading[]): Map<number, number> {
  const latest = new Map<number, { t: number; v: number }>();
  for (const r of readings) {
    const d = dayStart(r.measured_at);
    const t = Date.parse(r.measured_at);
    const cur = latest.get(d);
    if (!cur || t >= cur.t) latest.set(d, { t, v: r.val });
  }
  return new Map([...latest].map(([d, o]) => [d, o.v]));
}

export function moodSleepSeries(
  mood: StoredReading[],
  sleep: StoredReading[],
): { x: number[]; mood: (number | null)[]; sleep: (number | null)[] } {
  const m = perDay(mood);
  const s = perDay(sleep);
  const x = [...new Set([...m.keys(), ...s.keys()])].sort((a, b) => a - b);
  return { x, mood: x.map((d) => m.get(d) ?? null), sleep: x.map((d) => s.get(d) ?? null) };
}
