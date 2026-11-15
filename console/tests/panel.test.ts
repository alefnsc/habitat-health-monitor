import { describe, expect, test } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import type { Session } from "../src/contract";
import { axisStamp, chipSource, hhmmUtc } from "../src/format";
import { RULES } from "../src/model/rules";
import { bandSentence, compactSource } from "../src/model/panel/bands";
import { laneRules } from "../src/model/lanes";
import { exercisesDone } from "../src/model/panel/exercises";
import { holdMs, packetsInFlight } from "../src/model/panel/link";
import { missingLine } from "../src/model/panel/missing";
import { PLACES, placesWork } from "../src/model/panel/places";
import { weighTrend } from "../src/model/panel/trend";
import { SCREENS, screenFromHash } from "../src/screens";

const DAY = 86400;

describe("panel screen routing", () => {
  test("panel is first and the console default", () => {
    expect(SCREENS[0]).toBe("panel");
    expect(screenFromHash("")).toBe("panel");
    expect(screenFromHash("#/nope")).toBe("panel");
    expect(screenFromHash("#/lanes")).toBe("lanes");
  });
  test("a caller can name another fallback screen", () => {
    expect(screenFromHash("", "status")).toBe("status");
    expect(screenFromHash("#/panel", "status")).toBe("panel");
  });
});

describe("same lift, four places", () => {
  test("work scales with each place's gravity", () => {
    const rows = placesWork({ work_j: 40.2, g: 9.81 })!;
    expect(rows.map((r) => r.key)).toEqual(["earth", "moon", "mars", "iss"]);
    expect(rows[0].j).toBeCloseTo(40.2, 6);
    expect(rows[1].j).toBeCloseTo((40.2 * 1.62) / 9.81, 6);
    expect(rows[2].j).toBeCloseTo((40.2 * 3.73) / 9.81, 6);
    expect(rows[3].j).toBe(0);
  });
  test("a rep recorded at a simulated gravity is rescaled from its own g", () => {
    expect(placesWork({ work_j: 10, g: 3.73 })![0].j).toBeCloseTo((10 * 9.81) / 3.73, 6);
  });
  test("no rep or no usable g gives no rows", () => {
    expect(placesWork(null)).toBeNull();
    expect(placesWork({ work_j: 10, g: 0 })).toBeNull();
    expect(placesWork({ work_j: Number.NaN, g: 9.81 })).toBeNull();
  });
  test("gravity values carry their NASA source", () => {
    expect(PLACES.find((p) => p.key === "moon")!.g).toBe(1.62);
    expect(PLACES.find((p) => p.key === "mars")!.g).toBe(3.73);
  });
});

describe("weigh-in trend", () => {
  const t0 = Date.parse("2026-11-01T07:00:00Z") / 1000;
  test("needs 3 weigh-ins on 3 different days", () => {
    expect(weighTrend([]).fit).toBeNull();
    expect(weighTrend([{ t: t0, kg: 70 }, { t: t0 + 3600, kg: 70.2 }, { t: t0 + 7200, kg: 69.9 }]).fit).toBeNull();
    expect(weighTrend([{ t: t0, kg: 70 }, { t: t0 + DAY, kg: 70.2 }]).fit).toBeNull();
  });
  test("least-squares line, extended 30 days past the last weigh-in", () => {
    const pts = [{ t: t0, kg: 70 }, { t: t0 + DAY, kg: 69.9 }, { t: t0 + 2 * DAY, kg: 69.8 }];
    const { fit } = weighTrend(pts);
    expect(fit).not.toBeNull();
    expect(fit!.kgPerWeek).toBeCloseTo(-0.7, 6);
    expect(fit!.line[0]).toEqual([t0, expect.closeTo(70, 6)]);
    expect(fit!.line[1]).toEqual([t0 + 2 * DAY, expect.closeTo(69.8, 6)]);
    expect(fit!.extension[1][0]).toBe(t0 + 32 * DAY);
    expect(fit!.extension[1][1]).toBeCloseTo(69.8 - 3, 6);
  });
});

describe("Mars link packets", () => {
  const link = { state: "contact" as const, light_time_s: 720, time_scale: 60, queue_len: 0, last_blackout: null };
  test("hold time is the light time at the demo scale", () => {
    expect(holdMs(link)).toBe(12_000);
    expect(holdMs({ ...link, time_scale: 1 })).toBe(720_000);
  });
  test("each alert travels from Mars (0) to Earth (1), then leaves the line", () => {
    expect(packetsInFlight([1000, 7000, -20_000], 13_000, 12_000, "contact")).toEqual([1, 0.5]);
  });
  test("in a blackout or with no link simulator, alerts wait at Mars", () => {
    expect(packetsInFlight([1000], 2000, 12_000, "blackout")).toEqual([0]);
    expect(packetsInFlight([1000], 2000, 12_000, "unreachable")).toEqual([0]);
  });
});

describe("two-band sentence for the cabin", () => {
  test("watch: above the comfort zone, inside the health limit", () => {
    expect(bandSentence(RULES, "cabin_temp", 25.3)).toBe(
      "Above NASA's 20–25 °C comfort zone, inside its 18–27 °C health limit.",
    );
    expect(bandSentence(RULES, "cabin_rh", 68.2)).toBe("Above NASA's 30–60 % comfort zone, inside its 25–75 % health limit.");
    expect(bandSentence(RULES, "cabin_rh", 27)).toBe("Below NASA's 30–60 % comfort zone, inside its 25–75 % health limit.");
  });
  test("ok and outside", () => {
    expect(bandSentence(RULES, "cabin_temp", 22)).toBe("Inside NASA's 20–25 °C comfort zone and 18–27 °C health limit.");
    expect(bandSentence(RULES, "cabin_temp", 28)).toBe("Outside NASA's 18–27 °C health limit.");
  });
  test("compact source names the standard once with every requirement ID", () => {
    expect(compactSource(laneRules(RULES, "cabin_temp", "instant"))).toBe("NASA-STD-3001 [V2 6012] [V2 6013]");
    expect(compactSource([])).toBe("No rule");
  });
  test("indicators without the two NASA bands get no sentence", () => {
    expect(bandSentence(RULES, "hr", 95)).toBeNull();
  });
});

describe("panel helpers", () => {
  test("missing lanes are named with what would fill them", () => {
    expect(missingLine(["hr", "spo2", "sleep_h", "cabin_ppco2"])).toBe(
      "Not on this bench: heart rate, SpO2, sleep (ring import); cabin CO2 (cabin sensor node).",
    );
    expect(missingLine([])).toBeNull();
  });
  test("exercises done in the last 24 hours, in a fixed order", () => {
    const now = Date.parse("2026-11-15T15:00:00Z");
    const s = (exercise: Session["exercise"], started_at: string): Session => ({
      session: started_at, mass_kg: 5, g: 9.81, crew: null, started_at, ended_at: null, camera_reps: 3, load_cell_reps: 0,
      exercise,
    });
    expect(exercisesDone([
      s("row", "2026-11-15T14:00:00Z"), s("curl", "2026-11-15T13:00:00Z"), s("overhead_press", "2026-11-13T13:00:00Z"),
      s(null, "2026-11-15T12:00:00Z"),
    ], now)).toEqual(["curl", "row"]);
  });
  test("source chip prints the standard once", () => {
    expect(chipSource("NASA-STD-3001", "NASA-STD-3001 Vol 2 Rev F, 6.2.3.2 [V2 6013]")).toBe(
      "NASA-STD-3001 Vol 2 Rev F, 6.2.3.2 [V2 6013]",
    );
    expect(chipSource("NASA program document, not NASA-STD-3001", "JSC-67378")).toBe(
      "NASA program document, not NASA-STD-3001 JSC-67378",
    );
    expect(chipSource("NASA-STD-3001", null)).toBe("NASA-STD-3001");
  });
  test("time axis stamps are 24-hour UTC", () => {
    expect(hhmmUtc(Date.parse("2026-11-15T13:05:00Z") / 1000)).toBe("13:05");
    expect(hhmmUtc(Date.parse("2026-11-15T00:00:00Z") / 1000)).toBe("00:00");
    const t = Date.parse("2026-11-14T00:00:00Z") / 1000;
    expect(axisStamp(t, 6 * 3600)).toBe("00:00");
    expect(axisStamp(t, 7 * 86400)).toBe("11-14");
  });
  test("a window of minutes (a short recorded replay) gets seconds, so ticks do not repeat", () => {
    const t = Date.parse("2026-11-14T13:29:15Z") / 1000;
    expect(axisStamp(t, 193)).toBe("13:29:15");
    expect(axisStamp(t, 600)).toBe("13:29:15");
    expect(axisStamp(t, 601)).toBe("13:29");
  });
});

describe("palette", () => {
  const css = readFileSync(join(__dirname, "..", "src", "styles.css"), "utf8");
  const root = css.slice(css.indexOf(":root"), css.indexOf("}", css.indexOf(":root")));
  const vars = Object.fromEntries([...root.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
  const lum = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: string, b: string) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  test("text and status colours pass WCAG AA on cards", () => {
    for (const name of ["text", "text-2", "muted", "ok", "watch", "act", "unknown", "accent", "series"]) {
      expect(vars[name], name).toBeDefined();
      expect(ratio(vars[name], vars.panel), name).toBeGreaterThanOrEqual(4.5);
      expect(ratio(vars[name], vars.raised), name).toBeGreaterThanOrEqual(4.5);
    }
    for (const bg of ["watch-bg", "act-bg", "ok-bg"]) expect(ratio(vars.text, vars[bg]), bg).toBeGreaterThanOrEqual(4.5);
  });
  test("views take colours from the variables, not hard-coded hex values", () => {
    const dir = join(__dirname, "..", "src", "views");
    const files = (d: string): string[] => readdirSync(d, { withFileTypes: true })
      .flatMap((e) => (e.isDirectory() ? files(join(d, e.name)) : e.name.endsWith(".ts") ? [join(d, e.name)] : []));
    const hex = files(dir).filter((f) => /#[0-9a-fA-F]{6}\b/.test(readFileSync(f, "utf8")));
    expect(hex.map((f) => f.slice(dir.length + 1))).toEqual([]);
  });
  test("no company name anywhere in the console source", () => {
    const top = join(__dirname, "..");
    const files = (d: string): string[] => readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.name === "node_modules" || e.name.startsWith("dist") ? [] : e.isDirectory() ? files(join(d, e.name)) : [join(d, e.name)]);
    const name = ["voc", "aid"].join("");
    const hits = files(top).filter((f) => readFileSync(f, "utf8").toLowerCase().includes(name));
    expect(hits).toEqual([]);
  });
});
