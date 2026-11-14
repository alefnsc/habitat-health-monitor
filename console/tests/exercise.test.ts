import { describe, expect, test } from "vitest";
import { compareReps, formatWorkJ, nextSelected } from "../src/model/exercise";
import type { RepPair, Session, StoredRep } from "../src/contract";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const rep = (o: Partial<StoredRep>): StoredRep =>
  ({ v: 1, node: "camera", boot: 1, seq: 1, age_ms: 0, type: "rep", session: "s", rep: 1, src: "camera", peak_n: 200, work_j: 38.6, rom_m: 0.5, g: 9.81, mass_kg: 10, t0_ms: 0, t1_ms: 1, id: 1, measured_at: "x", ...o }) as StoredRep;
const pair = (n: number, cam: number | null, cell: number | null, o: Partial<RepPair> = {}): RepPair => ({
  rep: n, camera: cam === null ? null : rep({ rep: n, peak_n: cam }), load_cell: cell === null ? null : rep({ rep: n, src: "load_cell", peak_n: cell, rom_m: null }), work_cell_j: null, ...o,
});
const sess = (id: string): Session => ({ session: id, mass_kg: 10, g: 9.81, crew: null, started_at: "x", ended_at: null, camera_reps: 0, load_cell_reps: 0 });

describe("exercise", () => {
  test("test_pairs", () => {
    const r = compareReps({ session: "s", pairs: [pair(1, 210, 200), pair(2, 196, 200), pair(3, 206, 200)] });
    expect(r.rows.map((x) => x.diffN)).toEqual([10, -4, 6]);
    expect(r.rows.map((x) => x.diffPct)).toEqual([5.0, -2.0, 3.0]);
    expect(r.summary).toMatchObject({ meanPeakDiffN: 4.0, meanPeakDiffPct: 2.0, paired: 3, comparable: true });
  });

  test("test_unmatched", () => {
    const r = compareReps({ session: "s", pairs: [pair(1, 210, 200), pair(4, 100, null), pair(5, null, 100)] });
    expect(r.summary.unmatched).toBe(2);
    expect(r.summary.paired).toBe(1);
    expect(r.rows[1].cellPeakN).toBeNull();
    expect(r.rows[2].cameraPeakN).toBeNull();
    expect(r.rows[2].cameraWork).toBe("—");
    expect(r.summary.meanPeakDiffN).toBe(10);
  });

  test("test_null_rom", () => {
    const r = compareReps({ session: "s", pairs: [pair(1, null, 100)] });
    expect(r.rows[0].romM).toBe("—");
  });

  test("test_mixed_gravity", () => {
    const p = pair(1, 100, 100);
    p.camera = rep({ g: 3.71, peak_n: 100 });
    const r = compareReps({ session: "s", pairs: [p] });
    expect(r.summary.comparable).toBe(false);
    expect(r.summary.reason).toBe("Camera and load cell used different gravity; not compared.");
    expect(r.summary.meanPeakDiffN).toBeNull();
    expect(r.summary.meanPeakDiffPct).toBeNull();
  });

  test("test_zero_cell_peak", () => {
    const r = compareReps({ session: "s", pairs: [pair(1, 100, 0)] });
    expect(r.rows[0].diffPct).toBeNull();
    expect(JSON.stringify(r)).not.toContain("Infinity");
  });

  test("test_format_work_j", () => {
    const cases: [number, string][] = [[38.6, "38.6 J"], [120, "120 J"], [999, "999 J"], [999.6, "1.00 kJ"], [1000, "1.00 kJ"], [1234.5, "1.23 kJ"], [0, "0 J"]];
    for (const [j, s] of cases) expect(formatWorkJ(j)).toBe(s);
  });

  test("test_work_columns", () => {
    const a = pair(1, 100, 100, { work_cell_j: 37.9 });
    a.camera = rep({ work_j: 1234.5 });
    const b = pair(2, 100, 100, { work_cell_j: null });
    b.camera = rep({ work_j: 38.6 });
    const r = compareReps({ session: "s", pairs: [a, b] });
    expect(r.rows[0].cameraWork).toBe("1.23 kJ");
    expect(r.rows[0].cellWork).toBe("37.9 J (approx.)");
    expect(r.rows[1].cameraWork).toBe("38.6 J");
    expect(r.rows[1].cellWork).toBe("—");
    expect(JSON.stringify(r)).not.toMatch(/cal/i);
  });

  test("test_cell_work_label", () => {
    const text = readFileSync(join(__dirname, "..", "src", "copy.ts"), "utf8");
    expect(text).toContain("approx.: static cell force \\u00d7 camera displacement");
    expect(text.toLowerCase()).not.toContain("mean cell force");
  });

  test("test_replay_rows", () => {
    const p = pair(1, 100, 100);
    p.camera = rep({ node: "sim-1" });
    expect(compareReps({ session: "s", pairs: [p] }).rows[0].replay).toBe(true);
  });

  test("test_next_selected", () => {
    expect(nextSelected("s-1", [sess("s-2"), sess("s-1")], ["s-1"])).toBe("s-2");
    expect(nextSelected("s-1", [sess("s-2"), sess("s-1")], ["s-1", "s-2"])).toBe("s-1");
    expect(nextSelected(null, [], [])).toBeNull();
  });
});
