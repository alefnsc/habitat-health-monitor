// D45 signals: the wording model and the screen's cards, from hub-shaped signal objects.
import { describe, expect, test } from "vitest";
import type { Prompt, Signal, SignalsBody } from "../src/contract";
import { fmt, groupOf, headline, lagLines, limitLines, missingLines, notableCount, selfCheckFor } from "../src/model/signals";

const NOW = Date.parse("2026-11-20T10:00:00Z");

const sig = (over: Partial<Signal> = {}): Signal => ({
  id: "rest_hr_baseline", kind: "baseline", crew: "crew-a", state: "steady",
  headline_key: "signals.baseline.inside", value: { estimate: 57, low: 54.03, high: 59.97, unit: "bpm", per: null },
  method: { name: "own_baseline", ref: "median and MAD", alpha: null, n: 14, min_n: 7,
    window_start: "2026-11-06T10:00:00.000Z", window_end: "2026-11-20T10:00:00.000Z", coverage: null },
  inputs: [{ ind: "hr", src: "hobby", dev: "RING", node: "ring-1", n: 1000, first_at: "2026-11-06T03:00:00.000Z",
    last_at: "2026-11-20T09:00:00.000Z", oldest_age_s: 3600 }],
  missing: [], limits: ["signals.limit.ringEstimate"], reference: null, replay: false,
  series: [["2026-11-18T10:00:00.000Z", 56], ["2026-11-19T10:00:00.000Z", 57], ["2026-11-20T10:00:00.000Z", 57]],
  pairs: [], can_trigger: true, detail: {}, ...over,
});

describe("signals model", () => {
  test("baseline, trend, time-to-limit and missing wording", () => {
    expect(headline(sig())).toBe("Inside your own usual range: 57.0 bpm (usual 54.0 to 60.0).");
    expect(headline(sig({ kind: "trend", headline_key: "signals.trend.up",
      value: { estimate: 0.5, low: 0.31, high: 0.72, unit: "C", per: "h" } })))
      .toBe("Trend up: 0.50 °C per hour (interval 0.31 to 0.72).");
    expect(headline(sig({ id: "cabin_rh_ttl", kind: "time_to_limit", crew: null, headline_key: "signals.ttl.reaches",
      value: { estimate: 3.8, low: 3.4, high: 4.3, unit: "h", per: null },
      reference: { rule_id: "cabin_health_box_rh", source_kind: "nasa_std", limit: 75 },
      inputs: [{ ...sig().inputs[0], ind: "cabin_rh" }] })))
      .toBe("At this rate, reaches 75.0 % in 3.40 to 4.30 h, if nothing changes.");
    const nd = sig({ state: "not_enough_data", headline_key: "signals.nodata", value: null,
      missing: [{ key: "signals.missing.priorDays", need: 7, have: 4 }] });
    expect(headline(nd)).toBe("Not enough data yet.");
    expect(missingLines(nd)).toEqual(["Needs 7 earlier days for your usual range; has 4."]);
  });

  test("lag lines name every lag and pick none", () => {
    const s = sig({ id: "cabin_vs_earth", kind: "lagged_pair", crew: null, value: null, headline_key: "signals.pair.rho",
      detail: { lags: [{ lag_h: 0, n: 30, rho: 0.41, low: 0.06, high: 0.67 }, { lag_h: 1, n: 5, rho: null, low: null, high: null }] } });
    expect(lagLines(s)).toEqual([
      "0 h later: 30 pairs, rank correlation 0.41 (interval 0.06 to 0.67).",
      "1 h later: 5 pairs, too few to say anything.",
    ]);
  });

  test("groups, number format, notable count, open self-check", () => {
    expect(groupOf("cabin_rh_ttl")).toBe("cabin");
    expect(groupOf("water_14d")).toBe("food");
    expect(fmt(-0.123)).toBe("−0.12");
    const body: SignalsBody = { crew: null, at: "x", signals: [sig({ state: "notable" }), sig()] };
    expect(notableCount(body)).toBe(1);
    expect(notableCount(null)).toBe(0);
    const p = { id: 9, kind: "signal_body", crew: "crew-a", status: "open", created_at: "x", asks: ["symptom", "mood"],
      trigger_reading_id: null, rule_id: null,
      trigger: { signal_id: "rest_hr_baseline", state: "notable", headline_key: "x", value: null, inputs: [], limits: [],
        reference: null, replay: false, at: "x" } } as Prompt;
    expect(selfCheckFor([p], sig())?.id).toBe(9);
    expect(selfCheckFor([p], sig({ crew: "crew-c" }))).toBeUndefined();
  });

  test("reference limits name the weather model and the US Lab item only", () => {
    const [earth, iss] = limitLines(sig({ limits: ["signals.limit.earthReference", "signals.limit.issTelemetry"] }));
    expect(earth).toContain("weather-model values");
    expect(earth).toContain("coarse grid cell");
    expect(earth).toContain("not a station");
    expect(earth).toContain("not the bench itself");
    expect(iss).toContain("US Lab ppCO2 item only");
    expect(iss).not.toContain("Node 3");
  });
});
