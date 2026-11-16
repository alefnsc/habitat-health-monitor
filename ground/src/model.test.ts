import { describe, expect, it } from "vitest";
import {
  arrivalMs, asOfLabel, blackoutLabel, emptyView, indicatorLabel, orderedKeys, reduce, showsSynthetic,
  silenceLabel, sourceKindLabel,
} from "./model";
import type { Arrival, GroundView, OutboxItem } from "./types";

function reading(id: number, over: Record<string, unknown> = {}): OutboxItem {
  return {
    id, kind: "reading", created_at: "2026-11-15T13:00:00.000Z",
    payload: {
      id, measured_at: "2026-11-15T13:00:05.000Z", node: "vitals-1", boot: 1, seq: id,
      ind: "hr", val: 72, unit: "bpm", src: "hobby", q: ["ok"], crew: "crew-a",
      status: "ok", rule_id: null, source_kind: null, escalate_to: "self", ...over,
    },
  };
}
function alert(id: number, sec: number): OutboxItem {
  return {
    id, kind: "alert", created_at: "2026-11-15T13:00:00.000Z",
    payload: {
      id: `a${id}`, ind: "cabin_co2", status: "watch", prev_status: "ok", rule_id: "co2_1h",
      measured_at: `2026-11-15T13:00:${String(sec).padStart(2, "0")}.000Z`, crew: null,
      escalate_to: "cmo",
    },
  };
}
function arr(n: number, items: OutboxItem[], beacon: Arrival["beacon"] = null): Arrival {
  return { arrival_id: n, received_at: "x", beacon, items };
}
function fold(...arrivals: Arrival[]): GroundView {
  return arrivals.reduce((v, a) => reduce(v, a, 1000), emptyView());
}
const inds = (v: GroundView) => orderedKeys(v).map((k) => v.latest.get(k)!.ind);

describe("reduce", () => {
  it("counts_each_id_once", () => {
    const v = fold(arr(1, [reading(1), reading(2)]), arr(2, [reading(2), reading(3)]));
    expect(v.received).toBe(3);
  });
  it("latest_by_measured_at", () => {
    const v = fold(arr(1, [reading(1), reading(2, { val: 90, measured_at: "2026-11-15T13:00:01.000Z" })]));
    expect(v.latest.get("crew-a:hr")!.val).toBe(72);
  });
  it("status_from_payload", () => {
    const v = fold(arr(1, [reading(1, { ind: "cabin_co2", crew: null, val: 1800, unit: "ppm", status: "watch", rule_id: "co2_1h", source_kind: "nasa_std" })]));
    const e = v.latest.get("habitat:cabin_co2")!;
    expect([e.status, e.rule_id, e.source_kind]).toEqual(["watch", "co2_1h", "nasa_std"]);
  });
  it("flagged_greyed", () => {
    const e = fold(arr(1, [reading(1, { q: ["motion"], status: "act" })])).latest.get("crew-a:hr")!;
    expect(e.greyed).toBe(true);
    expect(e.status).toBe("unknown");
  });
  it("missing_status", () => {
    const e = fold(arr(1, [reading(1, { status: undefined })])).latest.get("crew-a:hr")!;
    expect(e.status).toBe("unknown");
  });
  it("alerts_capped_newest_first", () => {
    const items = Array.from({ length: 25 }, (_, i) => alert(i + 1, i + 1));
    const v = fold(arr(1, items));
    expect(v.alerts.length).toBe(20);
    expect(v.alerts[0].measured_at).toBe("2026-11-15T13:00:25.000Z");
    expect(v.alerts[0].prev_status).toBe("ok");
    expect(v.alerts[0].escalate_to).toBe("cmo");
  });
  it("rep_and_prompt_answer_counted", () => {
    const rep: OutboxItem = { id: 1, kind: "rep", created_at: "z", payload: {} };
    const pa: OutboxItem = { id: 2, kind: "prompt_answer", created_at: "z", payload: {} };
    const v = fold(arr(1, [rep, pa]));
    expect(v.received).toBe(2);
    expect(v.latest.size).toBe(0);
    expect(v.alerts.length).toBe(0);
  });
  it("beacon_updates_view", () => {
    const beacon = { link: { state: "contact", light_time_s: 720, time_scale: 60, queue_len: 7, last_blackout: null }, hold_s: 12, in_flight: 0, fetched_id: 0, delivered_id: 0, last_blackout_cause: null, sent_at: "z" } as const;
    let v = reduce(emptyView(), arr(1, [], beacon as unknown as Arrival["beacon"]), 1000);
    expect(v.beacon!.link.queue_len).toBe(7);
    expect(v.lastArrivalMs).toBe(1000);
    v = reduce(v, arr(2, [], null), 2000);
    expect(v.beacon!.link.queue_len).toBe(7);
  });
  it("intake_reading_shown_as_received", () => {
    const v = fold(arr(1, [reading(1, { ind: "intake_sodium_mg", val: 210, unit: "mg", status: "unknown" })]));
    const e = v.latest.get("crew-a:intake_sodium_mg")!;
    expect([e.val, e.unit]).toEqual([210, "mg"]);
    expect(indicatorLabel("intake_sodium_mg")).not.toMatch(/calorie|burned|balance/i);
  });
});

describe("labels", () => {
  it("as_of", () => {
    expect(asOfLabel(720, 60)).toBe("Earth's view, as of T − 12 min 00 s (simulated link; demo scale ×60 = 12 s)");
    expect(asOfLabel(1260, 1)).toBe("Earth's view, as of T − 21 min 00 s (simulated link; real scale)");
  });
  it("silence", () => {
    expect(silenceLabel(0, 37000)).toBe("No signal for 37 s");
    expect(silenceLabel(0, 2000)).toBe("");
    expect(silenceLabel(null, 5000)).toBe("Waiting for first contact");
  });
  it("blackout_labels", () => {
    const b = { start: "2026-11-15T13:00:30.000Z", end: "2026-11-15T13:01:00.000Z" };
    expect(blackoutLabel(b, "scheduled")).toBe("Last blackout: 13:00:30–13:01:00 UTC (scheduled, 30 s)");
    expect(blackoutLabel({ ...b, end: null }, "scheduled")).toBe("Blackout in progress since 13:00:30 UTC (scheduled)");
    expect(blackoutLabel(null, null)).toBe("No blackout yet");
    expect(blackoutLabel(b, null)).toContain("(cause unknown, 30 s)");
  });
  it("source_kind_labels", () => {
    expect(sourceKindLabel("nasa_std")).toBe("NASA-STD-3001");
    expect(sourceKindLabel("clinical_ref")).toBe("Clinical reference (not NASA-published)");
    expect(sourceKindLabel("personal_baseline")).toBe("Personal baseline");
    expect(sourceKindLabel("team_convention")).toBe("Team convention, not clinical");
    expect(sourceKindLabel(null)).toBe("");
  });
  it("indicator_labels_nutrition", () => {
    expect(indicatorLabel("intake_kcal")).toBe("Food energy logged");
    expect(indicatorLabel("intake_vitd_ug")).toBe("Vitamin D logged");
    expect(indicatorLabel("body_mass")).toBe("Body mass");
    expect(indicatorLabel("hr")).toBe("hr");
  });
});

describe("order", () => {
  const mk = (names: string[]) =>
    fold(arr(1, names.map((n, i) => reading(i + 1, { ind: n, crew: null }))));
  it("indicator_order", () => {
    expect(inds(mk(["cabin_co2", "mood", "hr", "glucose", "space_weather", "zzz_custom"]))).toEqual(
      ["hr", "glucose", "mood", "cabin_co2", "space_weather", "zzz_custom"]);
  });
  it("indicator_order_nutrition", () => {
    expect(inds(mk(["body_mass", "intake_sodium_mg", "intake_kcal", "rad_dose_cum", "hr"]))).toEqual(
      ["hr", "rad_dose_cum", "intake_kcal", "intake_sodium_mg", "body_mass"]);
  });
});

describe("synthetic readings and arrival time", () => {
  it("showsSynthetic is true only while a sim-1 reading is in the table", () => {
    expect(showsSynthetic(reduce(emptyView(), arr(1, [reading(1)]), 0))).toBe(false);
    const v = reduce(emptyView(), arr(1, [reading(1, { node: "sim-1" })]), 0);
    expect(v.latest.get("crew-a:hr")!.node).toBe("sim-1");
    expect(showsSynthetic(v)).toBe(true);
    const later = reduce(v, arr(2, [reading(2, { measured_at: "2026-11-15T13:00:09.000Z" })]), 0);
    expect(showsSynthetic(later)).toBe(false);
  });
  it("arrivalMs reads received_at and falls back when it is not a date", () => {
    expect(arrivalMs({ ...arr(1, []), received_at: "2026-11-15T13:00:05.000Z" }, 7)).toBe(
      Date.parse("2026-11-15T13:00:05.000Z"),
    );
    expect(arrivalMs(arr(1, []), 7)).toBe(7);
  });
});
