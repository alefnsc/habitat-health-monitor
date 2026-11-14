/**
 * Session record types, mirroring docs/strategy.md §3 ("Gravity and applied force
 * as first-class fields") in camelCase. Types only: no runtime code.
 */

export type Body = "EARTH" | "MOON" | "MARS" | "ISS" | "TRANSIT";
export type MassSource = "SCALE" | "SLAMMD" | "MANUAL_ENTRY";
export type Device = "ARED" | "T2" | "FERGO" | "FREE_WEIGHT" | "NONE";
export type LoadSource = "MANUAL_ENTRY" | "CAMERA" | "DEVICE";
export type Confidence = "LOW" | "MEDIUM" | "HIGH";

export interface Environment {
  gEnvMs2: number;
  body: Body;
  massKg: number;
  massSource: MassSource;
  massMeasuredAt: string; // ISO 8601
}

export interface AppliedLoad {
  device: Device;
  settingN: number | null;
  eccentricRatio: number | null;
  supportFraction: number | null; // T2 only: SLD as a fraction of 1 g body weight
}

export interface Provenance {
  loadSource: LoadSource;
  confidence: Confidence;
}
