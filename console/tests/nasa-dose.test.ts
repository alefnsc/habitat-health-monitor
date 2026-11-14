import { describe, expect, test } from "vitest";
import { doseBar } from "../src/model/nasa";
import type { IssReference } from "../src/contract";
import reference from "./fixtures/nasa/iss-reference.json";

const dose = (o: Partial<IssReference["dose"]> = {}): IssReference["dose"] => ({ ...(reference as unknown as IssReference).dose, ...o });

describe("dose budget", () => {
  test("test_pct", () => {
    expect(doseBar(dose({ effective_msv: 320, career_limit_msv: 600 })).pct).toBe(53.3);
    const over = doseBar(dose({ effective_msv: 700, career_limit_msv: 600 }));
    expect(over.pct).toBe(100);
    expect(over.effectiveText).toBe("700 mSv of 600 mSv");
  });

  test("test_markers", () => {
    expect(doseBar(dose({ career_limit_msv: 600 })).markers).toEqual([
      { pct: 50, label: "Watch at 50 % (300 mSv)" },
      { pct: 90, label: "Act at 90 % (540 mSv)" },
    ]);
  });

  test("test_absorbed_separate", () => {
    expect(doseBar(dose({ absorbed_mgy: 41.7 })).absorbedText).toBe("Absorbed dose 41.7 mGy (not comparable with the mSv limit)");
  });

  test("test_status_from_hub", () => {
    expect(doseBar(dose({ status: "watch", effective_msv: 100 })).statusCls).toBe("watch");
  });

  test("test_method", () => {
    expect(doseBar(dose({ effective_msv_method: "0.2–0.5 mSv/day ISS rate (NTRS 20250006168)" })).basisText).toBe(
      "Effective dose estimated: 0.2–0.5 mSv/day ISS rate (NTRS 20250006168)",
    );
  });

  test("test_no_effective", () => {
    const d = doseBar(dose({ effective_msv: null, absorbed_mgy: 41.7 }));
    expect(d.showBar).toBe(false);
    expect(d.effectiveText).toBe("Effective dose not available");
    expect(d.absorbedText).toContain("41.7 mGy");
  });

  test("test_profile", () => {
    expect(doseBar(dose({ profile: "ISS-like LEO", mission_day: 45 })).profileText).toBe("Profile: ISS-like LEO, mission day 45");
  });

  test("test_profile_not_set", () => {
    const d = doseBar(dose({ profile: null, mission_day: null, career_limit_msv: null, effective_msv: 90 }));
    expect(d.profileText).toBe("Profile: not set");
    expect(JSON.stringify(d)).not.toContain("null");
    expect(d.showBar).toBe(false);
    expect(d.markers).toEqual([]);
  });
});
