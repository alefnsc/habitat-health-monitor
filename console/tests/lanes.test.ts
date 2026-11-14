import { describe, expect, test } from "vitest";
import type { Ind, QualityFlag, RepsBody, SrcClass, StoredReading, StoredRep } from "../src/contract";
import type { ThresholdRule } from "../src/model/history";
import { RULES } from "../src/model/rules";
import {
  LANES, bandSlices, bandTicks, laneLayout, laneRules, laneSeries, laneTag, setWork, sharedX, sourceLine, statusOf, trailingMean, type LaneWindow,
  yRange,
} from "../src/model/lanes";
import { SCREENS, screenFromHash } from "../src/screens";

const rd = (
  ind: Ind, val: number, t: number, q: QualityFlag[] = ["ok"], src: SrcClass = "hobby", dev = "BME280",
): StoredReading => {
  const iso = new Date(t * 1000).toISOString();
  return {
    v: 1, node: "cabin-1", boot: 1, seq: 1, age_ms: 0, ind, val, unit: "u", src, dev, q, id: t,
    measured_at: iso, received_at: iso, derived_from: null,
  } as StoredReading;
};
const rule = (o: Partial<ThresholdRule>): ThresholdRule => ({
  id: "r", ind: "hr", window: "instant", ok: null, watch: null, act: null, source_kind: "clinical_ref", source_ref: "",
  url: "", note: "", ...o,
});
const slices = (ind: Ind, window: LaneWindow = "instant") =>
  bandSlices(laneRules(RULES, ind, window)).map((s) => [s.lo, s.hi, s.status]);

describe("lane bands from data/thresholds.json", () => {
  test("cabin temperature: NASA performance box inside the health box", () => {
    expect(slices("cabin_temp")).toEqual([
      [-Infinity, 18, "act"], [18, 20, "watch"], [20, 25, "ok"], [25, 27, "watch"], [27, Infinity, "act"],
    ]);
  });

  test("cabin humidity: 30-60 inside 25-75", () => {
    expect(slices("cabin_rh")).toEqual([
      [-Infinity, 25, "act"], [25, 30, "watch"], [30, 60, "ok"], [60, 75, "watch"], [75, Infinity, "act"],
    ]);
  });

  test("heart rate: NEWS2 rows", () => {
    expect(slices("hr")).toEqual([
      [-Infinity, 41, "act"], [41, 51, "watch"], [51, 90, "ok"], [90, 130, "watch"], [130, Infinity, "act"],
    ]);
  });

  test("CO2 band is the 1-hour-mean rule only", () => {
    expect(laneRules(RULES, "cabin_ppco2", "mean_1h").map((r) => r.id)).toEqual(["co2_1h"]);
    expect(slices("cabin_ppco2", "mean_1h")).toEqual([[-Infinity, 3, "ok"], [3, Infinity, "act"]]);
  });

  test("sleep: below 7 h is watch", () => {
    expect(slices("sleep_h")).toEqual([[-Infinity, 7, "watch"], [7, Infinity, "ok"]]);
  });

  test("cabin pressure has no rule, so no band", () => {
    expect(laneRules(RULES, "cabin_p", "instant")).toEqual([]);
    expect(bandSlices([])).toEqual([]);
  });
});

describe("point status", () => {
  test("worst rule wins", () => {
    const rs = laneRules(RULES, "cabin_temp", "instant");
    expect(statusOf(rs, 22)).toBe("ok");
    expect(statusOf(rs, 26)).toBe("watch");
    expect(statusOf(rs, 27.5)).toBe("act");
  });

  test("band edges follow the hub: min and max inclusive, lt and gt strict", () => {
    expect(statusOf([rule({ ok: { min: 20, max: 25 }, watch: {} })], 25)).toBe("ok");
    expect(statusOf([rule({ ok: { lt: 25 }, watch: {} })], 25)).toBe("watch");
    expect(statusOf([rule({ ok: { gt: 7 }, watch: {} })], 7)).toBe("watch");
  });

  test("no rule means unknown", () => {
    expect(statusOf([], 1013)).toBe("unknown");
  });
});

describe("source line", () => {
  test("cabin lanes name NASA-STD-3001 and the requirement numbers", () => {
    const s = sourceLine(laneRules(RULES, "cabin_temp", "instant"));
    expect(s).toContain("NASA-STD-3001");
    expect(s).toContain("[V2 6012]");
    expect(s).toContain("[V2 6013]");
  });

  test("vital-sign lanes keep the not-NASA-published label", () => {
    for (const ind of ["hr", "spo2", "sleep_h"] as Ind[]) {
      const s = sourceLine(laneRules(RULES, ind, "instant"));
      expect(s, ind).toContain("Clinical reference (not NASA-published)");
      expect(s, ind).not.toMatch(/^NASA/);
    }
    expect(sourceLine(laneRules(RULES, "hr", "instant"))).toContain("NEWS2");
  });

  test("one source per reference, no repeats", () => {
    const s = sourceLine(laneRules(RULES, "hr", "instant"));
    expect(s.split("NEWS2").length - 1).toBe(1);
  });

  test("no rule says so", () => {
    expect(sourceLine([])).toBe("No rule");
  });
});

describe("lane tag", () => {
  test("hobby sensors read as estimates", () => {
    expect(laneTag("cabin_temp", "hobby", "BME280")).toBe("Hobby sensor · Estimate");
    expect(laneTag("spo2", "hobby", "MAX30102")).toBe("Hobby sensor · Uncalibrated estimate");
  });

  test("other sources show their class only", () => {
    expect(laneTag("hr", "certified", "strap")).toBe("Certified device");
    expect(laneTag("sleep_h", "self", "manual")).toBe("Self-report");
  });
});

describe("lane series", () => {
  test("instant lane: in-band plain, out-of-band split by status, flagged greyed", () => {
    const rs = laneRules(RULES, "cabin_temp", "instant");
    const s = laneSeries([rd("cabin_temp", 26, 300), rd("cabin_temp", 22, 100), rd("cabin_temp", 28, 200),
      rd("cabin_temp", 23, 400, ["settling"])], rs, "instant");
    expect(s.x).toEqual([100, 200, 300, 400]);
    expect(s.raw).toEqual([22, 28, 26, null]);
    expect(s.mean).toBeNull();
    expect(s.watch).toEqual([null, null, 26, null]);
    expect(s.act).toEqual([null, 28, null, null]);
    expect(s.greyed).toEqual([null, null, null, 23]);
  });

  test("mean lane: status comes from the 1-hour mean, not the raw point", () => {
    const rs = laneRules(RULES, "cabin_ppco2", "mean_1h");
    const rows = [0, 900, 1800, 2700].map((t, i) => rd("cabin_ppco2", [2, 2, 2, 6][i], t));
    const s = laneSeries(rows, rs, "mean_1h");
    expect(s.mean).toEqual([null, null, null, 3]);
    expect(s.act).toEqual([null, null, null, null]);
    const hot = laneSeries([...rows, rd("cabin_ppco2", 6, 3000)], rs, "mean_1h");
    expect(hot.mean?.[4]).toBeCloseTo(3.6);
    expect(hot.act.slice(0, 4)).toEqual([null, null, null, null]);
    expect(hot.act[4]).toBeCloseTo(3.6);
  });
});

describe("trailing mean", () => {
  test("matches the hub: ok rows only, needs 45 min since the first one", () => {
    const rows = [rd("cabin_ppco2", 1, 0), rd("cabin_ppco2", 9, 600, ["assumed_pressure"]), rd("cabin_ppco2", 3, 2700),
      rd("cabin_ppco2", 5, 3500)];
    expect(trailingMean(rows)).toEqual([null, null, 2, 3]);
  });

  test("the window start is exclusive", () => {
    const rows = [rd("cabin_ppco2", 1, 0), rd("cabin_ppco2", 3, 900), rd("cabin_ppco2", 5, 3600)];
    expect(trailingMean(rows)).toEqual([null, null, 4]);
  });

  test("a gap longer than the window resets coverage", () => {
    const rows = [rd("cabin_ppco2", 1, 0), rd("cabin_ppco2", 1, 2700), rd("cabin_ppco2", 1, 9000)];
    expect(trailingMean(rows)).toEqual([null, 1, null]);
  });
});

describe("exercise work per set", () => {
  const rep = (session: string, n: number, work: number | null, t: number): StoredRep =>
    ({ session, rep: n, src: "camera", work_j: work, measured_at: new Date(t * 1000).toISOString() }) as StoredRep;
  const body = (session: string, reps: StoredRep[]): RepsBody => ({
    session, pairs: reps.map((r) => ({ rep: r.rep, camera: r, load_cell: null, work_cell_j: null })),
  });

  test("sums camera work per session, placed at the last rep with work", () => {
    const out = setWork([
      body("b", [rep("b", 1, 30, 500), rep("b", 2, 20, 520)]),
      body("a", [rep("a", 1, 40.2, 100), rep("a", 2, 38.5, 110), rep("a", 3, null, 120)]),
    ]);
    expect(out.map((s) => s.t)).toEqual([110, 520]);
    expect(out[0].j).toBeCloseTo(78.7);
    expect(out[0].reps).toBe(2);
    expect(out[1]).toEqual({ session: "b", t: 520, j: 50, reps: 2 });
  });

  test("a set with no camera work is left out", () => {
    const noCam: RepsBody = { session: "c", pairs: [{ rep: 1, camera: null, load_cell: null, work_cell_j: 12 }] };
    expect(setWork([noCam])).toEqual([]);
  });
});

describe("ranges", () => {
  test("y range reaches the nearest band edge on each side of the data", () => {
    const [lo, hi] = yRange([22, 26], bandSlices(laneRules(RULES, "cabin_temp", "instant")))!;
    expect(lo).toBeCloseTo(20 - 0.35);
    expect(hi).toBeCloseTo(27 + 0.35);
    const [hlo, hhi] = yRange([61, 67], bandSlices(laneRules(RULES, "hr", "instant")))!;
    expect(hlo).toBeCloseTo(51 - 1.95);
    expect(hhi).toBeCloseTo(90 + 1.95);
  });

  test("y range without bands is the data, padded; flat data gets a unit pad", () => {
    expect(yRange([1013, 1013], [])).toEqual([1012, 1014]);
    expect(yRange([], [])).toBeNull();
  });

  test("y ticks sit on the band edges inside the range", () => {
    const temp = bandSlices(laneRules(RULES, "cabin_temp", "instant"));
    expect(bandTicks(temp, [19.65, 27.35])).toEqual([20, 25, 27]);
    expect(bandTicks(bandSlices(laneRules(RULES, "cabin_ppco2", "mean_1h")), [0.4, 5.2])).toEqual([3]);
  });

  test("no band edge in range leaves the default ticks", () => {
    expect(bandTicks([], [1012, 1014])).toBeNull();
    expect(bandTicks(bandSlices(laneRules(RULES, "hr", "instant")), [60, 70])).toBeNull();
  });

  test("shared x spans every lane with data", () => {
    expect(sharedX([[100, 200], [], [50, 150]])).toEqual([50, 200]);
    expect(sharedX([[], []])).toBeNull();
    expect(sharedX([[100]])).toEqual([40, 160]);
  });
});

describe("lane list", () => {
  test("order follows the video: cabin, then vitals, then exercise", () => {
    expect(LANES.map((l) => l.key)).toEqual([
      "cabin_temp", "cabin_rh", "cabin_p", "cabin_ppco2", "hr", "spo2", "sleep_h", "work",
    ]);
  });

  test("pressure and CO2 are hidden when absent; other empty lanes collapse", () => {
    const byKey = Object.fromEntries(LANES.map((l) => [l.key, l]));
    expect(laneLayout(byKey.cabin_p, 0)).toBe("hidden");
    expect(laneLayout(byKey.cabin_ppco2, 0)).toBe("hidden");
    expect(laneLayout(byKey.spo2, 0)).toBe("empty");
    expect(laneLayout(byKey.work, 0)).toBe("empty");
    expect(laneLayout(byKey.cabin_p, 3)).toBe("chart");
  });
});

describe("navigation", () => {
  test("Lanes is a console screen", () => {
    expect(SCREENS).toContain("lanes");
    expect(screenFromHash("#/lanes")).toBe("lanes");
  });
});
