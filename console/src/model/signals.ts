// Signals (D45): pure wording of the hub's signal objects. Every word comes from COPY; the hub sends keys and numbers.
import { COPY } from "../copy";
import type { Prompt, Signal, SignalSnapshot, SignalsBody } from "../contract";
import { UNITS } from "../payload";

export type SignalGroup = "cabin" | "body" | "food" | "lift" | "cross";
export const GROUPS: SignalGroup[] = ["cabin", "body", "food", "lift", "cross"];

const GROUP_OF: Record<string, SignalGroup> = {
  cabin_temp_6h: "cabin", cabin_rh_6h: "cabin", cabin_temp_ttl: "cabin", cabin_rh_ttl: "cabin",
  cabin_ppco2_ttl: "cabin", iss_ppco2_6h: "cabin",
  rest_hr_baseline: "body", rest_hr_14n: "body", sleep_baseline: "body", spo2_baseline: "body",
  body_mass_30d: "food", water_14d: "food",
  lift_work_sets: "lift", lift_within_set: "lift", lift_tilt_agreement: "lift",
  cabin_vs_earth: "cross", training_vs_rest_hr: "cross", last_meal_vs_sleep: "cross", space_weather_vs_sleep: "cross",
};

export function groupOf(id: string): SignalGroup {
  return GROUP_OF[id] ?? "cross";
}

/** Two decimals under 10, one decimal above: the interval is the honest part, not the digits. */
export function fmt(x: number): string {
  const r = Math.abs(x) < 10 ? x.toFixed(2) : x.toFixed(1);
  return r.replace(/^-/, "−");
}

export function unitLabel(unit: string): string {
  if (unit === "C") return "°C";
  if (unit === "rho" || unit === "h") return unit === "h" ? "h" : "";
  return COPY[`signals.unit.${unit}`] ?? unit;
}

const fill = (t: string, v: Record<string, string | number>) =>
  Object.entries(v).reduce((s, [k, x]) => s.split(`{${k}}`).join(String(x)), t);

// `key` is the hub's own wording for the lag (signals.pair.lag | lagFew | lagNoSpread), when it sends one.
type Lag = { lag_h: number; n: number; rho: number | null; low: number | null; high: number | null; key?: string };
const PAIR_HEADLINES = new Set(["signals.pair.rho", "signals.pair.few", "signals.pair.noSpread"]);

function lagsOf(s: Signal | SignalSnapshot): Lag[] {
  const lags = "detail" in s ? s.detail.lags : undefined;
  return Array.isArray(lags) ? (lags as Lag[]) : [];
}

/** How many points a card is worked out from: for a pair read at several lags, the pairs across all of them. */
export function pointCount(s: Signal): number {
  const lags = lagsOf(s);
  return s.kind === "lagged_pair" && lags.length ? lags.reduce((a, l) => a + l.n, 0) : s.method.n;
}

/** The card's headline sentence. */
export function headline(s: Signal | SignalSnapshot): string {
  const t = COPY[s.headline_key] ?? COPY["signals.nodata"];
  const v = s.value;
  const n = "method" in s ? pointCount(s) : 0;
  const lags = lagsOf(s);
  // A pair read at several lags has no single value: each lag carries its own (lagLines), none is picked.
  if (!v && lags.length && PAIR_HEADLINES.has(s.headline_key)) {
    const hs = lags.map((l) => l.lag_h);
    return fill(COPY["signals.pair.lagged"], { from: Math.min(...hs), to: Math.max(...hs), n });
  }
  if (s.headline_key === "signals.ttl.reaches" && v) {
    const ind = s.inputs[0]?.ind;
    const unit = unitLabel((ind && (UNITS as Record<string, string>)[ind]) || "");
    return fill(t, { limit: fmt(s.reference?.limit ?? 0), unit, low: fmt(v.low), high: fmt(v.high) });
  }
  if (!v) return fill(t, { n });
  return fill(t, {
    est: fmt(v.estimate), low: fmt(v.low), high: fmt(v.high), unit: unitLabel(v.unit),
    per: v.per ? COPY[`signals.per.${v.per}`] ?? v.per : "", n,
  }).replace(/ {2,}/g, " ");
}

export function missingLines(s: Signal): string[] {
  return s.missing.map((m) => fill(COPY[m.key] ?? COPY["signals.nodata"], { need: m.need ?? "", have: m.have ?? "" }));
}

export function limitLines(s: Signal | SignalSnapshot): string[] {
  return s.limits.map((k) => COPY[k]).filter((x): x is string => typeof x === "string");
}

/** One line per lag for cabin_vs_earth (no lag is picked as the best one). */
export function lagLines(s: Signal): string[] {
  return lagsOf(s).map((l) => {
    if (l.rho === null || l.low === null || l.high === null) {
      const key = l.key === "signals.pair.lagNoSpread" ? l.key : "signals.pair.lagFew";
      return fill(COPY[key], { h: l.lag_h, n: l.n });
    }
    return fill(COPY["signals.pair.lag"], { h: l.lag_h, n: l.n, rho: fmt(l.rho), low: fmt(l.low), high: fmt(l.high) });
  });
}

/** Notable signals, real and replay counted apart: the two are never pooled into one number. */
export function notableCounts(body: SignalsBody | null): { real: number; replay: number } {
  const notable = (body?.signals ?? []).filter((s) => s.state === "notable");
  const replay = notable.filter((s) => s.replay).length;
  return { real: notable.length - replay, replay };
}

/** The open self-check prompt this signal opened, if any. */
export function selfCheckFor(prompts: Prompt[], s: Signal): Prompt | undefined {
  return prompts.find((p) => p.status === "open" && p.crew === s.crew
    && (p.kind === "signal_cabin" || p.kind === "signal_body")
    && (p.trigger as SignalSnapshot | null)?.signal_id === s.id);
}

/** Numbers of a series for a sparkline, in order; [time or rep, value] pairs from the hub. */
export function sparkValues(s: Signal): number[] {
  return s.series.map((p) => p[1]).filter((x) => Number.isFinite(x));
}

/** The side-by-side table: key, x, y (and the lag for cabin_vs_earth). A missing value stays an empty cell. */
export function pairRows(s: Signal): string[][] {
  return s.pairs.map((row) => row.map((c, i) => {
    if (i === 0) return String(c).slice(0, 16);
    if (typeof c !== "number" || !Number.isFinite(c)) return "";
    return i === 3 ? String(c) : fmt(c);
  }));
}
