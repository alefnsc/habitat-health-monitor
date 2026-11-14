import { describe, expect, test } from "vitest";
import {
  devLabel, estimateBadge, flagText, formatAge, formatTimeUtc, formatValue, sourceKindLabel, srcLabel, statusClass,
  statusLabel,
} from "../src/format";

describe("format", () => {
  test("test_format_decimals", () => {
    const cases: [string, number, string, string][] = [
      ["body_temp", 36.86, "C", "36.9 °C"],
      ["hr", 72.4, "bpm", "72 bpm"],
      ["cabin_ppco2", 2.4417, "mmHg", "2.44 mmHg"],
      ["cabin_p", 921.37, "hPa", "921.4 hPa"],
      ["cabin_co2", 812.6, "ppm", "813 ppm"],
      ["sleep_h", 7.25, "h", "7.3 h"],
      ["mood", 3, "1-5", "3 / 5"],
      ["glucose", 94, "mg/dL", "94 mg/dL"],
      ["rad_dose_cum", 123.46, "mSv", "123.5 mSv"],
    ];
    for (const [ind, v, u, out] of cases) expect(formatValue(ind, v, u)).toBe(out);
  });

  test("test_format_missing", () => {
    expect(formatValue("hr", null, "bpm")).toBe("—");
    expect(formatValue("hr", NaN, "bpm")).toBe("—");
    expect(formatValue("x", 1.234, "u")).toBe("1.234 u");
  });

  test("test_status_class", () => {
    expect(statusClass("act", ["ok"])).toBe("act");
    expect(statusClass("ok", ["motion"])).toBe("greyed");
    expect(statusClass("watch", ["ok", "settling"])).toBe("greyed");
    expect(statusClass("unknown", ["ok"])).toBe("unknown");
  });

  test("test_status_label", () => {
    expect(statusLabel("ok", ["ok"])).toBe("OK");
    expect(statusLabel("watch", ["ok"])).toBe("Watch");
    expect(statusLabel("act", ["ok"])).toBe("Act now");
    expect(statusLabel("unknown", ["ok"])).toBe("No rule");
    expect(statusLabel("ok", ["motion"])).toBe("Not assessed");
  });

  test("test_src_labels", () => {
    expect(srcLabel("certified")).toBe("Certified device");
    expect(srcLabel("hobby")).toBe("Hobby sensor");
    expect(srcLabel("self")).toBe("Self-report");
    expect(srcLabel("nasa")).toBe("NASA data");
    expect(srcLabel("replay")).toBe("Replay (recorded)");
    expect(sourceKindLabel("nasa_std")).toBe("NASA-STD-3001");
    expect(sourceKindLabel("clinical_ref")).toBe("Clinical reference (not NASA-published)");
    expect(sourceKindLabel("personal_baseline")).toBe("Your 30-day baseline");
    expect(sourceKindLabel("team_convention")).toBe("Team convention, not clinical");
    expect(sourceKindLabel("nasa_doc")).toBe("NASA program document, not NASA-STD-3001");
    expect(sourceKindLabel(null)).toBe("No rule");
  });

  test("test_estimate_badge", () => {
    expect(estimateBadge("spo2", "hobby", "MAX30102")).toBe("Uncalibrated estimate");
    expect(estimateBadge("skin_temp", "hobby", "MLX90614")).toBe("Forehead skin temperature, not core");
    expect(estimateBadge("skin_temp", "hobby", "DS18B20")).toBe("Skin temperature, not core");
    expect(estimateBadge("cabin_temp", "hobby", "DHT11")).toBe("DHT11 reads ±2 °C");
    expect(estimateBadge("cabin_temp", "hobby", "BME280")).toBeNull();
    expect(estimateBadge("hr", "certified", "H10")).toBeNull();
    expect(estimateBadge("hr", "self", "camera")).toBe("Estimate");
    expect(estimateBadge("load_raw", "hobby", "camera")).toBe("Estimate");
    // any other hobby-sensor vital is still labelled an estimate
    expect(estimateBadge("hr", "hobby", "MAX30102")).toBe("Estimate");
  });

  test("test_flag_text", () => {
    expect(flagText("motion")).toBe("Moved during reading");
    expect(flagText("no_contact")).toBe("No finger or probe contact");
    expect(flagText("settling")).toBe("Sensor warming up");
    expect(flagText("leads_off")).toBe("ECG leads off");
    expect(flagText("out_of_range")).toBe("Outside the sensor's range");
    expect(flagText("assumed_pressure")).toBe("Pressure assumed 1013.25 hPa");
    expect(flagText("stale")).toBe("NASA data older than its limit");
  });

  test("test_dev_label", () => {
    expect(devLabel("H10")).toBe("Chest strap");
    expect(devLabel("manual")).toBe("Typed in");
    expect(devLabel("camera")).toBe("Camera");
    expect(devLabel("MAX30102")).toBe("MAX30102");
  });

  test("test_format_age", () => {
    const cases: [number, string][] = [
      [0, "0 s ago"], [59, "59 s ago"], [60, "1 min ago"], [3599, "59 min ago"], [3600, "1 h ago"],
      [86399, "23 h ago"], [86400, "1 d ago"], [950400, "11 d ago"], [-5, "just now"],
    ];
    for (const [s, out] of cases) expect(formatAge(s)).toBe(out);
  });

  test("test_time_utc", () => {
    expect(formatTimeUtc("2026-11-14T15:04:05Z")).toBe("15:04 UTC");
  });
});
