import type {
  AlertEntry,
  Arrival,
  BlackoutCause,
  GroundView,
  LastBlackout,
  LatestEntry,
  Status,
} from "./types";

const MINUS = "−";
const TIMES = "×";
const ALERT_CAP = 20;

const ORDER = [
  "bp_sys", "bp_dia", "hr", "glucose", "body_temp", "sleep_h", "mood", "spo2", "skin_temp",
  "cabin_temp", "cabin_rh", "cabin_p", "cabin_co2", "cabin_ppco2", "cabin_lux", "space_weather",
  "rad_dose_cum", "intake_kcal", "intake_protein_g", "intake_carb_g", "intake_fat_g",
  "intake_water_ml", "intake_sodium_mg", "intake_potassium_mg", "intake_calcium_mg",
  "intake_iron_mg", "intake_vitd_ug", "body_mass",
];

const LABELS: Record<string, string> = {
  intake_kcal: "Food energy logged",
  intake_protein_g: "Protein logged",
  intake_carb_g: "Carbohydrate logged",
  intake_fat_g: "Fat logged",
  intake_water_ml: "Drinking fluid logged",
  intake_sodium_mg: "Sodium logged",
  intake_potassium_mg: "Potassium logged",
  intake_calcium_mg: "Calcium logged",
  intake_iron_mg: "Iron logged",
  intake_vitd_ug: "Vitamin D logged",
  body_mass: "Body mass",
};

const STATUSES: Status[] = ["ok", "watch", "act", "unknown"];

export function emptyView(): GroundView {
  return {
    beacon: null,
    lastArrivalMs: null,
    received: 0,
    latest: new Map(),
    alerts: [],
    seen: new Set(),
  };
}

function asStatus(v: unknown): Status {
  return STATUSES.includes(v as Status) ? (v as Status) : "unknown";
}

/**
 * Fold one arrival into the view. Returns a new view; `seen` is shared and
 * mutated in place so long replays stay linear.
 */
export function reduce(view: GroundView, arrival: Arrival, nowMs: number): GroundView {
  const latest = new Map(view.latest);
  let alerts = view.alerts;
  let received = view.received;
  const seen = view.seen;

  for (const item of arrival.items) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    received += 1;
    const p = item.payload;
    if (item.kind === "reading") {
      const q: unknown[] = Array.isArray(p.q) ? p.q : [];
      const flagged = q.some((f) => f !== "ok");
      const crew: string | null = p.crew ?? null;
      const key = `${crew ?? "habitat"}:${p.ind}`;
      const prev = latest.get(key);
      if (prev && prev.measured_at > p.measured_at) continue;
      const entry: LatestEntry = {
        ind: p.ind,
        val: p.val,
        unit: p.unit,
        status: flagged ? "unknown" : asStatus(p.status),
        rule_id: p.rule_id ?? null,
        src: p.src,
        source_kind: p.source_kind ?? null,
        measured_at: p.measured_at,
        crew,
        greyed: flagged,
      };
      latest.set(key, entry);
    } else if (item.kind === "alert") {
      const a: AlertEntry = {
        id: p.id,
        ind: p.ind,
        status: asStatus(p.status),
        prev_status: asStatus(p.prev_status),
        rule_id: p.rule_id ?? null,
        measured_at: p.measured_at,
        crew: p.crew ?? null,
        escalate_to: p.escalate_to ?? null,
      };
      alerts = [a, ...alerts]
        .sort((x, y) => (x.measured_at < y.measured_at ? 1 : x.measured_at > y.measured_at ? -1 : 0))
        .slice(0, ALERT_CAP);
    }
  }

  return {
    beacon: arrival.beacon ?? view.beacon,
    lastArrivalMs: nowMs,
    received,
    latest,
    alerts,
    seen,
  };
}

function two(n: number): string {
  return String(n).padStart(2, "0");
}

export function asOfLabel(lightTimeS: number, timeScale: number): string {
  const min = Math.floor(lightTimeS / 60);
  const sec = Math.round(lightTimeS % 60);
  const base = `Earth's view, as of T ${MINUS} ${min} min ${two(sec)} s`;
  if (timeScale > 1) {
    const hold = Math.round(lightTimeS / timeScale);
    return `${base} (simulated link; demo scale ${TIMES}${timeScale} = ${hold} s)`;
  }
  return `${base} (simulated link; real scale)`;
}

export function silenceLabel(lastArrivalMs: number | null, nowMs: number): string {
  if (lastArrivalMs === null) return "Waiting for first contact";
  const s = (nowMs - lastArrivalMs) / 1000;
  return s > 3 ? `No signal for ${Math.floor(s)} s` : "";
}

function hms(iso: string): string {
  return iso.slice(11, 19);
}

export function blackoutLabel(
  last: LastBlackout | null,
  cause: BlackoutCause | null,
): string {
  if (!last) return "No blackout yet";
  if (last.end === null) {
    return `Blackout in progress since ${hms(last.start)} UTC (${cause ?? "cause unknown"})`;
  }
  const secs = Math.round((Date.parse(last.end) - Date.parse(last.start)) / 1000);
  return `Last blackout: ${hms(last.start)}–${hms(last.end)} UTC (${cause ?? "cause unknown"}, ${secs} s)`;
}

export function sourceKindLabel(kind: string | null): string {
  switch (kind) {
    case "nasa_std":
      return "NASA-STD-3001";
    case "clinical_ref":
      return "Clinical reference (not NASA-published)";
    case "personal_baseline":
      return "Personal baseline";
    case "team_convention":
      return "Team convention, not clinical";
    default:
      return "";
  }
}

export function indicatorLabel(ind: string): string {
  return LABELS[ind] ?? ind;
}

export function orderedKeys(view: GroundView): string[] {
  const rank = (ind: string) => {
    const i = ORDER.indexOf(ind);
    return i === -1 ? ORDER.length : i;
  };
  return [...view.latest.entries()]
    .sort(([ka, a], [kb, b]) => {
      const d = rank(a.ind) - rank(b.ind);
      if (d !== 0) return d;
      if (a.ind !== b.ind) return a.ind < b.ind ? -1 : 1;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    })
    .map(([k]) => k);
}
