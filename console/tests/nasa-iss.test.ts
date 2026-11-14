import { describe, expect, test } from "vitest";
import { ageClass, issVsHabitat, refCo2 } from "../src/model/nasa";
import type { IssCabin, IssReference, StatusEntry } from "../src/contract";
import cabin from "./fixtures/nasa/iss-cabin.json";
import reference from "./fixtures/nasa/iss-reference.json";

const iss = (items: IssCabin["items"] = (cabin as unknown as IssCabin).items, o: Partial<IssCabin> = {}): IssCabin => ({ ...(cabin as unknown as IssCabin), items, ...o });
const ref = (o: Partial<IssReference> = {}): IssReference => ({ ...(reference as unknown as IssReference), ...o });
const hab = (ind: StatusEntry["ind"], val: number, unit: string): StatusEntry => ({
  ind, val, unit, status: "ok", rule_id: null, source_kind: null, source_ref: null, guidance_id: null, escalate_to: "self",
  measured_at: "2026-11-14T12:00:00Z", crew: null, src: "hobby", dev: "BME280", q: ["ok"], node: "cabin-1", reading_id: 1,
});
const NOW = Date.parse("2026-11-14T12:00:00Z");
const row = (r: ReturnType<typeof issVsHabitat>, label: string) => r.rows.find((x) => x.label.includes(label))!;

describe("ISS cabin vs habitat", () => {
  test("test_age_class", () => {
    expect(ageClass({ age_s: 20, stale: false }, "live")).toEqual({ label: "Live", cls: "ok" });
    expect(ageClass({ age_s: 300, stale: false }, "live")).toEqual({ label: "Latest: 5 min ago", cls: "ok" });
    expect(ageClass({ age_s: 950400, stale: true }, "live")).toEqual({ label: "Stale: updated 11 d ago", cls: "watch" });
    expect(ageClass({ age_s: 5, stale: false }, "recorded")).toEqual({ label: "Recorded capture", cls: "greyed" });
  });

  test("test_pressure_row", () => {
    const r = row(issVsHabitat(iss(), ref(), [hab("cabin_p", 921.4, "hPa")], NOW), "pressure");
    expect(r.issLive).toBe("759.3 mmHg (1012.3 hPa)");
    expect(r.habitat).toBe("921.4 hPa");
  });

  test("test_co2_row", () => {
    const r = row(issVsHabitat(iss(), ref(), [hab("cabin_ppco2", 2.1, "mmHg")], NOW), "CO2 partial");
    expect(r.habitat).toBe("2.10 mmHg");
    expect(r.issLive).toBe("2.44 mmHg");
    expect(r.issLiveAge).toBe("Stale: updated 11 d ago");
    expect(r.limit).toBe("≤ 3.0 mmHg 1-hour mean [V2 6004]");
  });

  test("test_missing_item", () => {
    const r = row(issVsHabitat(iss((cabin as unknown as IssCabin).items.filter((i) => i.name !== "cabin_temperature")), ref(), [], NOW), "temperature");
    expect(r.issLive).toBe("—");
    expect(r.issLiveAge).toBe("No data");
  });

  test("test_iss_unavailable", () => {
    const r = issVsHabitat(null, ref(), [], NOW);
    for (const x of r.rows) { expect(x.issLive).toBe("—"); expect(x.issLiveAge).toBe("No data"); }
    expect(r.footnote).toContain("ISS Live not available on this hub.");
  });

  test("test_ref_co2_key", () => {
    expect(refCo2(ref().cabin)).toEqual({ val: 2.6, unit: "mmHg" });
    expect(row(issVsHabitat(iss(), ref(), [], NOW), "CO2 partial").issRef).toBe("2.60 mmHg (mean)");
    const nullCo2 = ref({ cabin: { ...ref().cabin!, co2_mmhg: null } });
    expect(refCo2(nullCo2.cabin)).toBeNull();
    expect(row(issVsHabitat(iss(), nullCo2, [], NOW), "CO2 partial").issRef).toBe("—");
  });

  test("test_ref_cabin_null", () => {
    const r = issVsHabitat(iss(), ref({ cabin: null }), [], NOW);
    expect(refCo2(null)).toBeNull();
    for (const x of r.rows) expect(x.issRef).toBe("—");
  });

  test("test_ref_ignores_raw_unit", () => {
    const r = issVsHabitat(iss(), ref({ cabin: { ...ref().cabin!, co2_raw_unit: "RAWUNIT" } }), [], NOW);
    expect(JSON.stringify(r)).not.toContain("RAWUNIT");
  });

  test("test_unit_note", () => {
    const note = "Feed labels pressure PSI; values are mmHg by magnitude.";
    expect(issVsHabitat(iss(undefined, { unit_note: note }), ref(), [], NOW).footnote).toContain(note);
  });
});
