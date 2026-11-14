import { describe, expect, test } from "vitest";
import { defaultWindow, moodSleepSeries, thresholdLines, toSeries, type ThresholdRule } from "../src/model/history";
import type { Ind, QualityFlag, StoredReading } from "../src/contract";

const rd = (ind: Ind, val: number, atIso: string, q: QualityFlag[] = ["ok"]): StoredReading => ({
  v: 1, node: "manual", boot: 1, seq: 1, age_ms: 0, ind, val, unit: "u", src: "self", dev: "manual", q, id: 1,
  measured_at: atIso, received_at: atIso, derived_from: null,
});
const at = (s: number) => new Date(s * 1000).toISOString();
const rule = (o: Partial<ThresholdRule>): ThresholdRule => ({
  id: "r", ind: "hr", window: "instant", ok: null, watch: null, act: null, source_kind: "clinical_ref", source_ref: "",
  url: "", note: "", ...o,
});

describe("history model", () => {
  test("test_series_split", () => {
    const s = toSeries([rd("hr", 70, at(100)), rd("hr", 95, at(200), ["motion"]), rd("hr", 72, at(300))]);
    expect(s).toEqual({ x: [100, 200, 300], assessed: [70, null, 72], greyed: [null, 95, null] });
  });

  test("test_series_sorted", () => {
    expect(toSeries([rd("hr", 1, at(300)), rd("hr", 2, at(100)), rd("hr", 3, at(200))]).x).toEqual([100, 200, 300]);
  });

  test("test_threshold_lines_co2", () => {
    const r = rule({ id: "co2_1h", ind: "cabin_ppco2", window: "mean_1h", ok: { max: 3.0 }, watch: null, act: {} });
    expect(thresholdLines([r], "cabin_ppco2")).toEqual({ lines: [{ y: 3.0, label: "co2_1h (1-hour mean)" }], skipped: [] });
  });

  test("test_threshold_lines_two_edges", () => {
    const r = rule({ id: "cabin_health_box_temp", ind: "cabin_temp", ok: { min: 18, max: 27 }, act: {} });
    expect(thresholdLines([r], "cabin_temp").lines).toEqual([
      { y: 18, label: "cabin_health_box_temp (instant)" },
      { y: 27, label: "cabin_health_box_temp (instant)" },
    ]);
  });

  test("test_threshold_lines_dedupe", () => {
    const a = rule({ id: "hr_rest_high", ok: { max: 90 }, watch: { max: 130 }, act: {} });
    expect(thresholdLines([a], "hr").lines.map((l) => l.y)).toEqual([90, 130]);
    const b = rule({ id: "dose", ind: "rad_dose_cum", ok: { lt: 299.9 }, watch: { gt: 299.9 }, act: {} });
    expect(thresholdLines([b], "rad_dose_cum").lines.map((l) => l.y)).toEqual([299.9]);
  });

  test("test_threshold_skip", () => {
    const r = rule({ id: "lux_general", ind: "cabin_lux", ok: {}, watch: null, act: null });
    expect(thresholdLines([r], "cabin_lux")).toEqual({ lines: [], skipped: ["lux_general"] });
  });

  test("test_other_ind_ignored", () => {
    const r = rule({ id: "rh", ind: "cabin_rh", ok: { min: 25, max: 75 } });
    expect(thresholdLines([r], "cabin_temp")).toEqual({ lines: [], skipped: [] });
  });

  test("test_default_window", () => {
    expect(defaultWindow("cabin_ppco2")).toEqual({ sinceIsoOffsetH: 6, limit: 5000 });
    expect(defaultWindow("cabin_temp")).toEqual({ sinceIsoOffsetH: 6, limit: 5000 });
    expect(defaultWindow("hr")).toEqual({ sinceIsoOffsetH: 168, limit: 2000 });
    expect(defaultWindow("sleep_h")).toEqual({ sinceIsoOffsetH: 720, limit: 60 });
    expect(defaultWindow("mood")).toEqual({ sinceIsoOffsetH: 720, limit: 60 });
  });

  test("test_mood_sleep_series", () => {
    const mood = [rd("mood", 2, "2026-11-12T08:00:00Z"), rd("mood", 2, "2026-11-13T08:00:00Z"), rd("mood", 3, "2026-11-14T08:00:00Z")];
    const sleep = [rd("sleep_h", 6.5, "2026-11-12T07:00:00Z"), rd("sleep_h", 5.0, "2026-11-14T07:00:00Z")];
    const day = (d: string) => Date.parse(d) / 1000;
    const r = moodSleepSeries(mood, sleep);
    expect(r.x).toEqual([day("2026-11-12T00:00:00Z"), day("2026-11-13T00:00:00Z"), day("2026-11-14T00:00:00Z")]);
    expect(r.mood).toEqual([2, 2, 3]);
    expect(r.sleep).toEqual([6.5, null, 5.0]);
    const twice = moodSleepSeries([rd("mood", 1, "2026-11-12T08:00:00Z"), rd("mood", 4, "2026-11-12T20:00:00Z")], []);
    expect(twice.mood).toEqual([4]);
    expect(moodSleepSeries(mood, []).sleep).toEqual([null, null, null]);
  });
});
