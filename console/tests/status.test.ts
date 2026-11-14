import { describe, expect, test } from "vitest";
import { BOARD_LAYOUT, applyAssessment, applySnapshot, buildTiles } from "../src/model/status";
import type { CrewId, Ind, QualityFlag, SourceKind, SrcClass, Status, StatusBody, StatusEntry } from "../src/contract";

const NOW = Date.parse("2026-11-14T12:00:00Z");

function entry(ind: Ind, val: number, o: Partial<StatusEntry> = {}): StatusEntry {
  const units: Record<string, string> = { hr: "bpm", bp_sys: "mmHg", bp_dia: "mmHg", glucose: "mg/dL", spo2: "%", mood: "1-5" };
  return {
    ind, val, unit: units[ind] ?? "u", status: "ok" as Status, rule_id: "r1", source_kind: "clinical_ref" as SourceKind,
    source_ref: "ref", guidance_id: "g1", escalate_to: "self", measured_at: "2026-11-14T11:59:50Z", crew: null,
    src: "certified" as SrcClass, dev: "manual", q: ["ok"] as QualityFlag[], node: "manual", reading_id: 1, ...o,
  };
}
const tile = (tiles: ReturnType<typeof buildTiles>, id: string) => tiles.find((t) => t.id === id)!;

describe("status model", () => {
  test("test_layout", () => {
    expect(BOARD_LAYOUT.vitals.map((t) => t.id)).toEqual(["bp", "hr", "glucose", "body_temp", "sleep_h", "mood"]);
    expect(BOARD_LAYOUT.vitals[0].inds).toEqual(["bp_sys", "bp_dia"]);
    expect(BOARD_LAYOUT.supporting.map((t) => t.id)).toEqual(["spo2", "skin_temp"]);
    expect(BOARD_LAYOUT.cabin.map((t) => t.id)).toEqual([
      "cabin_ppco2", "cabin_temp", "cabin_rh", "cabin_p", "cabin_lux", "cabin_co2",
    ]);
  });

  test("test_bp_combined", () => {
    let t = tile(buildTiles([entry("bp_sys", 128, { status: "watch" }), entry("bp_dia", 82)], NOW), "bp");
    expect(t.value).toBe("128/82 mmHg");
    expect(t.statusClass).toBe("watch");
    t = tile(buildTiles([entry("bp_sys", 128, { status: "watch" })], NOW), "bp");
    expect(t.value).toBe("128/— mmHg");
    expect(t.statusClass).toBe("unknown");
  });

  test("test_missing_indicator", () => {
    const t = tile(buildTiles([], NOW), "glucose");
    expect(t.value).toBe("—");
    expect(t.statusLabel).toBe("No reading yet");
    expect(t.statusClass).toBe("unknown");
  });

  test("test_source_on_every_tile", () => {
    const tiles = buildTiles([entry("hr", 70), entry("mood", 3, { source_kind: "team_convention", src: "self" }),
      entry("glucose", 90, { source_kind: null, rule_id: null, status: "unknown" })], NOW);
    for (const id of ["hr", "mood", "glucose"]) {
      const t = tile(tiles, id);
      expect(t.srcLabel).not.toBe("");
      expect(t.sourceKindLabel).not.toBe("");
    }
    expect(tile(tiles, "glucose").sourceKindLabel).toBe("No rule");
    expect(tile(tiles, "mood").sourceKindLabel).toBe("Team convention, not clinical");
  });

  test("test_greyed_flags", () => {
    const t = tile(buildTiles([entry("hr", 72, { q: ["motion"], status: "unknown", rule_id: null })], NOW), "hr");
    expect(t.statusClass).toBe("greyed");
    expect(t.flags).toEqual(["Moved during reading"]);
  });

  test("test_body_temp_not_substituted", () => {
    const tiles = buildTiles([entry("skin_temp", 33.1, { src: "hobby", dev: "DS18B20" })], NOW);
    expect(tile(tiles, "body_temp").value).toBe("—");
    expect(tile(tiles, "skin_temp").value).toBe("33.1 u");
  });

  test("test_snapshot_replaces", () => {
    const body: StatusBody = { crew: null, generated_at: "x", nodes: [], results: [entry("hr", 70)] };
    expect(applySnapshot(body).map((e) => [e.ind, e.val])).toEqual([["hr", 70]]);
  });

  test("test_assessment_update", () => {
    const base = [entry("hr", 70, { measured_at: "2026-11-14T10:00:00Z" })];
    const newer = applyAssessment(base, entry("hr", 74, { measured_at: "2026-11-14T10:01:00Z" }));
    expect(newer.map((e) => e.val)).toEqual([74]);
    const older = applyAssessment(newer, entry("hr", 60, { measured_at: "2026-11-14T09:59:00Z" }));
    expect(older.map((e) => e.val)).toEqual([74]);
    const added = applyAssessment(newer, entry("glucose", 90));
    expect(added).toHaveLength(2);
  });

  test("test_post_results_applied", () => {
    const results = [entry("glucose", 95)];
    const entries = results.reduce(applyAssessment, [] as StatusEntry[]);
    const t = tile(buildTiles(entries, NOW), "glucose");
    expect(t.value).toBe("95 mg/dL");
    expect(t.statusClass).toBe("ok");
  });

  test("test_all_crew_chip", () => {
    const tiles = buildTiles([entry("hr", 70, { crew: "crew-b" as CrewId }), entry("cabin_temp", 22)], NOW);
    expect(tile(tiles, "hr").crewChip).toBe("Crew B");
    expect(tile(tiles, "cabin_temp").crewChip).toBeNull();
  });

  test("test_not_on_board", () => {
    const entries = [entry("space_weather", 1), entry("rad_dose_cum", 5), entry("body_mass", 70), entry("intake_kcal", 1),
      entry("intake_vitd_ug", 1)];
    const tiles = buildTiles(entries, NOW);
    const ids = tiles.map((t) => t.id);
    for (const bad of ["space_weather", "rad_dose_cum", "body_mass", "intake_kcal", "intake_vitd_ug"]) {
      expect(ids).not.toContain(bad);
    }
    for (const t of tiles) expect(t.value).toBe("—");
  });

  test("test_age", () => {
    const t = tile(buildTiles([entry("hr", 70, { measured_at: new Date(NOW - 90_000).toISOString() })], NOW), "hr");
    expect(t.ageText).toBe("1 min ago");
  });

  test("honesty: badges and requirement id", () => {
    const t = tile(buildTiles([entry("spo2", 97, { src: "hobby", dev: "MAX30102", q: ["motion"] }),
      entry("cabin_ppco2", 2.4, { source_kind: "nasa_std", source_ref: "NASA-STD-3001 Vol 2 [V2 6004]" })], NOW), "spo2");
    expect(t.value).toBe("97 %");
    expect(t.badges).toContain("Uncalibrated estimate");
    expect(t.srcLabel).toBe("Hobby sensor");
    const c = tile(buildTiles([entry("cabin_ppco2", 2.4, { source_kind: "nasa_std", source_ref: "[V2 6004]" })], NOW), "cabin_ppco2");
    expect(c.sourceRef).toBe("[V2 6004]");
  });
});

describe("waiting for a window", () => {
  test("rule exists, status unknown: names the window and the source, not No rule", () => {
    const e = entry("cabin_ppco2", 2.4, { status: "unknown", rule_id: "co2_1h", source_kind: null, source_ref: null });
    const t = buildTiles([e], NOW).find((x) => x.id === "cabin_ppco2")!;
    expect(t.statusLabel).toBe("Waiting for 1-hour mean (NASA-STD-3001 [V2 6004])");
    expect(t.statusClass).toBe("unknown");
    expect(t.statusLabel).not.toBe("No rule");
  });
  test("no rule id: still No rule", () => {
    const e = entry("glucose", 90, { status: "unknown", rule_id: null, source_kind: null });
    expect(buildTiles([e], NOW).find((x) => x.id === "glucose")!.statusLabel).toBe("No rule");
  });
});
