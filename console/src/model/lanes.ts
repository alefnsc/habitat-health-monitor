import type { Ind, RepsBody, SrcClass, StoredReading, StoredRep } from "../contract";
import { COPY } from "../copy";
import { estimateBadge, sourceKindLabel, srcLabel } from "../format";
import type { Band, ThresholdRule } from "./history";

export type LaneStatus = "ok" | "watch" | "act" | "unknown";
export type LaneWindow = "instant" | "mean_1h";

export interface LaneSpec {
  key: string;
  ind: Ind | null; // null: the exercise lane, built from reps, not readings
  label: string;
  unit: string;
  window: LaneWindow;
  optional: boolean; // hidden, not collapsed, when there is no data
}

export const LANES: LaneSpec[] = [
  { key: "cabin_temp", ind: "cabin_temp", label: "Cabin temperature", unit: "C", window: "instant", optional: false },
  { key: "cabin_rh", ind: "cabin_rh", label: "Cabin humidity", unit: "%", window: "instant", optional: false },
  { key: "cabin_p", ind: "cabin_p", label: "Cabin pressure", unit: "hPa", window: "instant", optional: true },
  { key: "cabin_ppco2", ind: "cabin_ppco2", label: "Cabin CO2 (partial pressure)", unit: "mmHg", window: "mean_1h", optional: true },
  { key: "hr", ind: "hr", label: "Heart rate", unit: "bpm", window: "instant", optional: false },
  { key: "spo2", ind: "spo2", label: "SpO2", unit: "%", window: "instant", optional: false },
  { key: "sleep_h", ind: "sleep_h", label: "Sleep", unit: "h", window: "instant", optional: false },
  { key: "work", ind: null, label: "Exercise work per set", unit: "J", window: "instant", optional: false },
];

export interface BandSlice {
  lo: number;
  hi: number;
  status: LaneStatus;
}

const RANK: Record<LaneStatus, number> = { unknown: 0, ok: 1, watch: 2, act: 3 };
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const ts = (r: { measured_at: string }) => Date.parse(r.measured_at) / 1000;
const flagged = (r: StoredReading) => r.q.some((f) => f !== "ok");

// Same edges as hub/thresholds.py Band.contains: min and max inclusive, lt and gt strict.
function contains(b: Band, x: number): boolean {
  if (isNum(b.min) && x < b.min) return false;
  if (isNum(b.max) && x > b.max) return false;
  if (isNum(b.lt) && !(x < b.lt)) return false;
  return !(isNum(b.gt) && !(x > b.gt));
}

function ruleStatus(rule: ThresholdRule, x: number): LaneStatus {
  for (const name of ["ok", "watch", "act"] as const) {
    const b = rule[name];
    if (b && contains(b, x)) return name;
  }
  return "unknown";
}

/** Worst status across the rules; "unknown" with no rules. */
export function statusOf(rules: ThresholdRule[], x: number): LaneStatus {
  let worst: LaneStatus = "unknown";
  for (const r of rules) {
    const s = ruleStatus(r, x);
    if (RANK[s] > RANK[worst]) worst = s;
  }
  return worst;
}

export function laneRules(rules: ThresholdRule[], ind: Ind, window: LaneWindow): ThresholdRule[] {
  return rules.filter((r) => r.ind === ind && r.window === window);
}

/** The value axis cut at every band edge, each slice with the worst status inside it. */
export function bandSlices(rules: ThresholdRule[]): BandSlice[] {
  const edges = [
    ...new Set(
      rules.flatMap((r) => [r.ok, r.watch, r.act].flatMap((b) => (b ? [b.min, b.max, b.lt, b.gt].filter(isNum) : []))),
    ),
  ].sort((a, b) => a - b);
  if (!edges.length) return [];
  const bounds = [-Infinity, ...edges, Infinity];
  const out: BandSlice[] = [];
  for (let i = 0; i < bounds.length - 1; i++) {
    const lo = bounds[i];
    const hi = bounds[i + 1];
    const probe = lo === -Infinity ? hi - 1 : hi === Infinity ? lo + 1 : (lo + hi) / 2;
    const status = statusOf(rules, probe);
    const last = out[out.length - 1];
    if (last && last.status === status) last.hi = hi;
    else out.push({ lo, hi, status });
  }
  return out;
}

function shortRef(ref: string, kind: string): string {
  const end = ref.lastIndexOf("]");
  const s = end >= 0 ? ref.slice(0, end + 1) : ref;
  return s.startsWith(`${kind} `) ? s.slice(kind.length + 1) : s;
}

/** "NASA-STD-3001 · Vol 2 Rev F, … [V2 6012]; …", or the existing "No rule" label. */
export function sourceLine(rules: ThresholdRule[]): string {
  if (!rules.length) return COPY["kind.none"];
  const groups = new Map<string, string[]>();
  for (const r of rules) {
    const kind = sourceKindLabel(r.source_kind);
    const refs = groups.get(kind) ?? [];
    const ref = shortRef(r.source_ref, kind);
    if (!refs.includes(ref)) refs.push(ref);
    groups.set(kind, refs);
  }
  return [...groups].map(([kind, refs]) => `${kind} · ${refs.join("; ")}`).join(" | ");
}

/** Source class of the latest reading; hobby sensors always carry an estimate badge. */
export function laneTag(ind: Ind, src: SrcClass, dev: string): string {
  const badge = estimateBadge(ind, src, dev) ?? (src === "hobby" ? COPY["badge.hobbyGeneric"] : null);
  return badge ? `${srcLabel(src)} · ${badge}` : srcLabel(src);
}

/**
 * Trailing mean at each row's time, as hub/assess.py computes mean_1h: ok rows in (t - window, t],
 * and only once the earliest of them is at least `coverageS` old. Rows must be in ascending time order.
 */
export function trailingMean(rows: StoredReading[], windowS = 3600, coverageS = 2700): (number | null)[] {
  const ok: { t: number; v: number }[] = [];
  let lo = 0;
  let sum = 0;
  return rows.map((r) => {
    const t = ts(r);
    if (!flagged(r)) {
      ok.push({ t, v: r.val });
      sum += r.val;
    }
    while (lo < ok.length && ok[lo].t <= t - windowS) sum -= ok[lo++].v;
    const n = ok.length - lo;
    return n > 0 && t - ok[lo].t >= coverageS ? sum / n : null;
  });
}

export interface LaneSeries {
  x: number[];
  raw: (number | null)[];
  mean: (number | null)[] | null;
  watch: (number | null)[];
  act: (number | null)[];
  greyed: (number | null)[];
}

/** Split readings into the drawn series. Out-of-band status is judged on the mean for a mean_1h lane. */
export function laneSeries(readings: StoredReading[], rules: ThresholdRule[], window: LaneWindow): LaneSeries {
  const rows = [...readings].sort((a, b) => ts(a) - ts(b));
  const raw = rows.map((r) => (flagged(r) ? null : r.val));
  const mean = window === "mean_1h" ? trailingMean(rows) : null;
  const judged = mean ?? raw;
  const pick = (s: LaneStatus) => judged.map((v) => (v !== null && statusOf(rules, v) === s ? v : null));
  return {
    x: rows.map(ts), raw, mean, watch: pick("watch"), act: pick("act"),
    greyed: rows.map((r) => (flagged(r) ? r.val : null)),
  };
}

export interface SetWork {
  session: string;
  t: number;
  j: number;
  reps: number;
}

/** Camera work summed per session (one set), placed at the last rep that has work. */
export function setWork(bodies: RepsBody[]): SetWork[] {
  const out: SetWork[] = [];
  for (const b of bodies) {
    const cams = b.pairs.map((p) => p.camera).filter((c): c is StoredRep => !!c && isNum(c.work_j));
    if (!cams.length) continue;
    out.push({
      session: b.session,
      t: Math.max(...cams.map(ts)),
      j: cams.reduce((s, c) => s + (c.work_j as number), 0),
      reps: cams.length,
    });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Data range stretched to the nearest band edge below and above it, plus 5 % padding. */
export function yRange(values: (number | null)[], slices: BandSlice[]): [number, number] | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (!isNum(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Infinity) return null;
  const edges = slices.flatMap((s) => [s.lo, s.hi]).filter(isNum);
  const below = edges.filter((e) => e <= lo);
  const above = edges.filter((e) => e >= hi);
  if (below.length) lo = Math.max(...below);
  if (above.length) hi = Math.min(...above);
  const pad = hi > lo ? (hi - lo) * 0.05 : 1;
  return [lo - pad, hi + pad];
}

/** Band edges inside the y range, used as the lane's y ticks; null keeps uPlot's own ticks. */
export function bandTicks(slices: BandSlice[], range: [number, number]): number[] | null {
  const edges = [...new Set(slices.flatMap((s) => [s.lo, s.hi]))].filter((e) => isNum(e) && e >= range[0] && e <= range[1]);
  return edges.length ? edges.sort((a, b) => a - b) : null;
}

/** One time range for every lane: earliest to latest point across lanes. */
export function sharedX(xs: number[][]): [number, number] | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const a of xs) {
    for (const t of a) {
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
  }
  if (lo === Infinity) return null;
  return hi > lo ? [lo, hi] : [lo - 60, hi + 60];
}

export function laneLayout(spec: LaneSpec, points: number): "chart" | "empty" | "hidden" {
  if (points > 0) return "chart";
  return spec.optional ? "hidden" : "empty";
}
