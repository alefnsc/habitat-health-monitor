import { COPY } from "./copy";
import type { Ind, QualityFlag, SourceKind, SrcClass, Status } from "./contract";

const DECIMALS: Record<string, number> = {
  hr: 0, spo2: 0, bp_sys: 0, bp_dia: 0, glucose: 0, cabin_rh: 0, cabin_co2: 0, cabin_lux: 0, load_raw: 0,
  space_weather: 0,
  body_temp: 1, skin_temp: 1, cabin_temp: 1, cabin_p: 1, sleep_h: 1, rad_dose_cum: 1,
  cabin_ppco2: 2, motion: 2,
};

export function formatValue(ind: Ind | string, val: number | null, unit: string): string {
  if (val === null || val === undefined || Number.isNaN(val)) return COPY["status.none"];
  const d = DECIMALS[ind];
  const num = d === undefined ? String(val) : val.toFixed(d);
  if (unit === "1-5") return `${num} / 5`;
  if (unit === "code") return num;
  if (unit === "C") return `${num} °C`;
  return unit ? `${num} ${unit}` : num;
}

const hasFlag = (q: QualityFlag[]) => q.some((f) => f !== "ok");

export function statusClass(status: Status, q: QualityFlag[]): "ok" | "watch" | "act" | "unknown" | "greyed" {
  return hasFlag(q) ? "greyed" : status;
}

export function statusLabel(status: Status, q: QualityFlag[]): string {
  return hasFlag(q) ? COPY["status.notAssessed"] : COPY[`status.${status}`];
}

export function srcLabel(src: SrcClass): string {
  return COPY[`src.${src}`];
}

export function sourceKindLabel(kind: SourceKind | null): string {
  return COPY[kind ? `kind.${kind}` : "kind.none"];
}

export function estimateBadge(ind: Ind, src: SrcClass, dev: string): string | null {
  if (dev === "camera") return COPY["badge.camera"];
  if (src !== "hobby") return null;
  if (ind === "spo2" && dev === "MAX30102") return COPY["badge.spo2Hobby"];
  if (ind === "skin_temp") return dev === "MLX90614" ? COPY["badge.skinForehead"] : COPY["badge.skinProbe"];
  if (ind === "cabin_temp" && dev === "DHT11") return COPY["badge.dht11"];
  if (dev === "MAX30102") return COPY["badge.hobbyGeneric"];
  return null;
}

export function flagText(flag: QualityFlag): string {
  return COPY[`flag.${flag}`] ?? flag;
}

export function devLabel(dev: string): string {
  return COPY[`dev.${dev}`] ?? dev;
}

export function formatAge(seconds: number): string {
  if (seconds < 0) return COPY["age.justNow"];
  if (seconds < 60) return `${Math.floor(seconds)} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export function formatTimeUtc(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC`;
}
