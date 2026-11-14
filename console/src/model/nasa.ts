import type { CrewId, IssCabin, IssReference, SpaceWeather, StatusEntry } from "../contract";
import { COPY } from "../copy";
import { formatAge, formatTimeUtc, formatValue } from "../format";
import { RULES } from "./rules";
import type { Band, ThresholdRule } from "./history";

const CREW_LABEL: Record<CrewId, string> = { "crew-a": COPY["crew.a"], "crew-b": COPY["crew.b"], "crew-c": COPY["crew.c"] };
const DASH = COPY["status.none"];
const minutes = (iso: string, nowMs: number) => Math.max(0, Math.floor((nowMs - Date.parse(iso)) / 60000));

// ---- space-weather banner ----

export function weatherBanner(sw: SpaceWeather, nowMs: number) {
  const mins = sw.cached_at ? minutes(sw.cached_at, nowMs) : null;
  const cachedText =
    mins === null
      ? COPY["nasa.noData"]
      : sw.stale
        ? `Cached data, ${mins} min old`
        : sw.status === "ok"
          ? `Space weather quiet, checked ${mins} min ago`
          : `Checked ${mins} min ago`;
  const cls: "ok" | "watch" | "act" | "greyed" = sw.status === "unknown" || (sw.stale && sw.status === "ok") ? "greyed" : sw.status;
  let title =
    sw.status === "act" ? COPY["nasa.titleAct"]
    : sw.status === "watch" ? `${COPY["nasa.titleWatch"]}: ${sw.reason}`
    : sw.status === "unknown" ? COPY["nasa.titleUnknown"]
    : COPY["nasa.titleStale"];
  const replay = sw.mode === "replay";
  if (replay) {
    const day = sw.event_time ? ` of ${sw.event_time.slice(0, 10)}` : "";
    title = `Replay (recorded event${day}): ${title}`;
  }
  const disclaimer = sw.disclaimer?.trim() ? sw.disclaimer : COPY["nasa.disclaimerFallback"];
  const detail = [sw.reason, cachedText, disclaimer].filter(Boolean).join(". ").replace(/\.\./g, ".");
  const ackable = sw.status === "act" || sw.status === "watch";
  const ackText = !ackable ? null : sw.ack ? `Acknowledged by ${CREW_LABEL[sw.ack.crew]} at ${formatTimeUtc(sw.ack.at)}` : COPY["nasa.notAcked"];
  return { show: sw.status !== "ok" || sw.stale, cls, title, detail, cachedText, replay, link: sw.link, ackText };
}

export function ackState(sw: SpaceWeather, crew: CrewId | null): { enabled: boolean; hint: string | null } {
  if (!(sw.status === "act" || sw.status === "watch") || sw.ack) return { enabled: false, hint: null };
  if (crew === null) return { enabled: false, hint: COPY["nasa.chooseAck"] };
  return { enabled: true, hint: null };
}

// ---- ISS cabin vs habitat ----

export function ageClass(item: { age_s: number; stale: boolean }, mode: "live" | "recorded"): { label: string; cls: "ok" | "watch" | "greyed" } {
  if (mode === "recorded") return { label: COPY["nasa.recorded"], cls: "greyed" };
  if (item.stale) return { label: `Stale: updated ${formatAge(item.age_s)}`, cls: "watch" };
  if (item.age_s < 60) return { label: COPY["nasa.live"], cls: "ok" };
  return { label: `Latest: ${formatAge(item.age_s)}`, cls: "ok" };
}

export function refCo2(cabin: IssReference["cabin"]): { val: number; unit: string } | null {
  return cabin?.co2_mmhg ? { val: cabin.co2_mmhg.mean, unit: "mmHg" } : null;
}

export interface ComparisonRow {
  label: string;
  habitat: string;
  issLive: string;
  issLiveAge: string;
  issRef: string;
  limit: string;
}

const refId = (r: ThresholdRule) => r.source_ref.match(/\[[^\]]+\]/)?.[0] ?? "";
const num = (x: number) => (Number.isInteger(x) ? x.toFixed(1) : String(x));
const rule = (id: string) => RULES.find((r) => r.id === id);
const bandOf = (r: ThresholdRule): Band => r.ok ?? {};

function limitText(id: string, kind: "max" | "range", unit: string, window = ""): string {
  const r = rule(id);
  if (!r) return DASH;
  const b = bandOf(r);
  const tag = refId(r);
  if (kind === "max" && b.max !== undefined) return `≤ ${num(b.max)} ${unit}${window ? ` ${window}` : ""} ${tag}`.trim();
  if (kind === "range" && b.min !== undefined && b.max !== undefined) return `${b.min}–${b.max} ${unit} ${tag}`.trim();
  return DASH;
}

export function issVsHabitat(
  iss: IssCabin | null,
  ref: IssReference | null,
  habitat: StatusEntry[],
  _nowMs: number,
): { rows: ComparisonRow[]; footnote: string[] } {
  const hab = (ind: StatusEntry["ind"]) => {
    const e = habitat.find((x) => x.ind === ind);
    return e ? formatValue(e.ind, e.val, e.unit) : DASH;
  };
  const live = (name: string, f: (i: IssCabin["items"][number]) => string) => {
    const it = iss?.items.find((i) => i.name === name);
    if (!it || !iss) return { v: DASH, age: COPY["nasa.noData2"] };
    return { v: f(it), age: ageClass(it, iss.mode).label };
  };
  const c = ref?.cabin ?? null;
  const refCell = (s: { mean: number } | null | undefined, ind: StatusEntry["ind"], unit: string) =>
    s ? `${formatValue(ind, s.mean, unit)} (mean)` : DASH;
  const p = live("cabin_pressure", (i) => `${i.val.toFixed(1)} ${i.unit}${i.val_hpa !== null ? ` (${i.val_hpa.toFixed(1)} hPa)` : ""}`);
  const t = live("cabin_temperature", (i) => formatValue("cabin_temp", i.val, i.unit));
  const co2 = live("lab_ppco2", (i) => formatValue("cabin_ppco2", i.val, i.unit));
  const co2ref = refCo2(c);
  const rows: ComparisonRow[] = [
    { label: COPY["tile.cabin_p"], habitat: hab("cabin_p"), issLive: p.v, issLiveAge: p.age, issRef: DASH, limit: DASH },
    { label: COPY["tile.cabin_temp"], habitat: hab("cabin_temp"), issLive: t.v, issLiveAge: t.age, issRef: refCell(c?.temperature_c, "cabin_temp", "C"), limit: limitText("cabin_health_box_temp", "range", "°C") },
    { label: COPY["tile.cabin_ppco2"], habitat: hab("cabin_ppco2"), issLive: co2.v, issLiveAge: co2.age, issRef: co2ref ? `${formatValue("cabin_ppco2", co2ref.val, co2ref.unit)} (mean)` : DASH, limit: limitText("co2_1h", "max", "mmHg", "1-hour mean") },
    { label: COPY["tile.cabin_rh"], habitat: hab("cabin_rh"), issLive: DASH, issLiveAge: COPY["nasa.noData2"], issRef: refCell(c?.rh_pct, "cabin_rh", "%"), limit: limitText("cabin_health_box_rh", "range", "%") },
  ];
  const footnote: string[] = [];
  if (!iss) footnote.push(COPY["nasa.issUnavailable"]);
  else if (iss.unit_note) footnote.push(iss.unit_note);
  return { rows, footnote };
}

// ---- dose budget ----

const n1 = (x: number) => String(Number(x.toFixed(1)));

export function doseBar(d: IssReference["dose"]) {
  const eff = d.effective_msv;
  const lim = d.career_limit_msv;
  const showBar = eff !== null && lim !== null && lim > 0;
  return {
    showBar,
    pct: showBar ? Math.min(100, Math.round(((eff as number) / (lim as number)) * 1000) / 10) : 0,
    markers: showBar
      ? ([50, 90] as const).map((pct) => ({ pct, label: `${pct === 50 ? "Watch" : "Act"} at ${pct} % (${n1((lim as number) * pct / 100)} mSv)` }))
      : [],
    effectiveText: eff === null ? COPY["nasa.noEffective"] : lim !== null ? `${n1(eff)} mSv of ${n1(lim)} mSv` : `${n1(eff)} mSv`,
    absorbedText: d.absorbed_mgy === null ? COPY["nasa.noAbsorbed"] : `Absorbed dose ${n1(d.absorbed_mgy)} mGy (not comparable with the mSv limit)`,
    statusCls: d.status,
    basisText: d.effective_msv_method ? `Effective dose estimated: ${d.effective_msv_method}` : "",
    profileText: d.profile === null ? COPY["nasa.profileNone"] : `Profile: ${d.profile}${d.mission_day !== null ? `, mission day ${d.mission_day}` : ""}`,
  };
}
