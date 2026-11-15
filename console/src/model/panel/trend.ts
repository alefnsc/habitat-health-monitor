// Least-squares trend of logged weigh-ins, extended 30 days. Arithmetic on the crew's own entries, not a prediction.
const DAY_S = 86400;
export const EXTEND_DAYS = 30;
const MIN_POINTS = 3;
const MIN_DAYS = 3;

export interface WeighIn {
  t: number; // seconds
  kg: number;
}

export interface TrendFit {
  kgPerWeek: number;
  line: [[number, number], [number, number]];
  extension: [[number, number], [number, number]];
}

export function weighTrend(points: WeighIn[]): { fit: TrendFit | null } {
  const pts = points.filter((p) => Number.isFinite(p.t) && Number.isFinite(p.kg)).sort((a, b) => a.t - b.t);
  const days = new Set(pts.map((p) => Math.floor(p.t / DAY_S)));
  if (pts.length < MIN_POINTS || days.size < MIN_DAYS) return { fit: null };
  const n = pts.length;
  const mt = pts.reduce((s, p) => s + p.t, 0) / n;
  const mk = pts.reduce((s, p) => s + p.kg, 0) / n;
  const sxx = pts.reduce((s, p) => s + (p.t - mt) ** 2, 0);
  const slope = pts.reduce((s, p) => s + (p.t - mt) * (p.kg - mk), 0) / sxx; // kg per second
  const at = (t: number) => mk + slope * (t - mt);
  const t0 = pts[0].t;
  const t1 = pts[n - 1].t;
  const t2 = t1 + EXTEND_DAYS * DAY_S;
  return {
    fit: {
      kgPerWeek: slope * 7 * DAY_S,
      line: [[t0, at(t0)], [t1, at(t1)]],
      extension: [[t1, at(t1)], [t2, at(t2)]],
    },
  };
}
