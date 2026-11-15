// @vitest-environment jsdom
// Render tests for the panel cards: mount each card in jsdom with hub-shaped data and read its text.
import { describe, expect, test, vi } from "vitest";
import type { ExerciseDay, RepPair, RepsBody, Session, StoredRep, TiltWitness } from "../src/contract";
import { liftCard, placesCard } from "../src/views/panel/lift";
import { massCard } from "../src/views/panel/mass";

// uPlot draws on a canvas, which jsdom does not have.
vi.mock("uplot", () => ({ default: class { static tzDate(d: Date) { return d; } destroy() {} } }));

const NOW = Date.parse("2026-11-15T18:00:00Z");
const clock = { replay: false, now: () => NOW };
const STARTED = "2026-11-15T17:50:00.000Z";

const session = (over: Partial<Session> = {}): Session => ({
  session: "s1", mass_kg: 10, g: 9.81, crew: "crew-a", started_at: STARTED, ended_at: null,
  camera_reps: 3, load_cell_reps: 0, exercise: null, ...over,
});

const rep = (n: number, work: number, g = 9.81): StoredRep => ({
  v: 1, node: "camera", boot: 1, seq: n, age_ms: 0, type: "rep", session: "s1", rep: n, src: "camera",
  peak_n: 100, work_j: work, rom_m: 0.4, g, mass_kg: 10, t0_ms: 0, t1_ms: 2000, exercise: null,
  id: n, measured_at: `2026-11-15T17:5${n}:00.000Z`,
});

const witness = (seen: boolean, inside: boolean, offset: number | null): TiltWitness => ({
  seen, turn_inside: inside, offset_ms: offset, rise_at: null, fall_at: null,
});

const reps = (pairs: Partial<RepPair>[]): RepsBody => ({
  session: "s1",
  pairs: pairs.map((p, i) => ({ rep: i + 1, camera: null, load_cell: null, work_cell_j: null, ...p })),
});

const day = (over: Partial<ExerciseDay> = {}): ExerciseDay => ({
  window_start: "2026-11-14T18:00:00Z", window_end: "2026-11-15T18:00:00Z", sessions: 1, camera_reps: 3,
  camera_work_j: 120, cell_work_j: null, replay: false, excluded_reps: 0, ...over,
});

const text = (n: Element) => n.textContent ?? "";

describe("lift card", () => {
  test("one bar per camera rep and the set total", () => {
    const c = liftCard(clock);
    c.update({ session: session(), reps: reps([{ camera: rep(1, 40) }, { camera: rep(2, 42) }, { camera: rep(3, 38) }]) });
    expect(c.node.querySelectorAll(".bar")).toHaveLength(3);
    expect(text(c.node)).toContain("3 reps");
    expect(text(c.node)).toContain("120");
  });

  test("no session or no camera rep says so", () => {
    const c = liftCard(clock);
    c.update({ session: null, reps: null });
    expect(c.node.querySelectorAll(".bar")).toHaveLength(0);
    expect(text(c.node)).toContain("No set");
  });

  test("tilt witness line: reps seen, turnaround inside, median offset", () => {
    const c = liftCard(clock);
    c.update({
      session: session(),
      reps: reps([
        { camera: rep(1, 40), tilt: witness(true, true, 190) },
        { camera: rep(2, 42), tilt: witness(true, true, 230) },
        { camera: rep(3, 38), tilt: witness(false, false, null) },
      ]),
    });
    const line = [...c.node.querySelectorAll("p.tilt")].map(text);
    expect(line).toEqual([
      "Tilt switch (tilt-1): seen on 2 of 3 reps, turnaround inside the tilt on 2. Median offset +210 ms (the 200 ms debounce makes it read late).",
    ]);
  });

  test("no tilt line when the hub sent no witness (replay, older hub, reps without a turnaround)", () => {
    const c = liftCard(clock);
    c.update({ session: session(), reps: reps([{ camera: rep(1, 40) }, { camera: rep(2, 42), tilt: null }]) });
    expect(c.node.querySelector("p.tilt")).toBeNull();
  });

  test("no change seen in the whole set is said plainly, with no offset", () => {
    const c = liftCard(clock);
    c.update({ session: session(), reps: reps([{ camera: rep(1, 40), tilt: witness(false, false, null) }]) });
    expect(text(c.node.querySelector("p.tilt")!)).toBe("Tilt switch (tilt-1): seen on 0 of 1 reps, turnaround inside the tilt on 0.");
  });
});

describe("four places card", () => {
  test("the last rep at Earth, Moon, Mars and the station, Mars at the NSSDC 3.73", () => {
    const c = placesCard(clock);
    c.update({ session: session(), reps: reps([{ camera: rep(1, 40) }, { camera: rep(2, 98.1) }]) });
    const rows = [...c.node.querySelectorAll(".place")].map(text);
    expect(rows).toHaveLength(4);
    expect(rows[2]).toContain("3.73 m/s²");
    expect(text(c.node)).toContain("rep 2");
  });
});

describe("mass card", () => {
  const base = { weighIns: [], food: null, sessions: [] };

  test("training work left out at a simulated gravity says why, with the count", () => {
    const c = massCard(clock);
    c.update({ ...base, training: day({ camera_reps: 0, camera_work_j: null, excluded_reps: 3 }) });
    expect(text(c.node)).toContain("Reps at a simulated gravity are left out: 3");
    c.dispose();
  });

  test("no footnote when nothing was left out", () => {
    const c = massCard(clock);
    c.update({ ...base, training: day() });
    expect(text(c.node)).not.toContain("left out");
    c.dispose();
  });
});
