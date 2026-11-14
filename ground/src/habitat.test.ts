import { describe, expect, it } from "vitest";
import { FLASH_MS, emptyLit, litSpots, noteArrival, spotsFor, spotsInFile } from "./habitat";
import type { Arrival, Beacon, ItemKind, ReplayFile } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function item(kind: ItemKind, payload: Record<string, any>) {
  return { id: 1, kind, created_at: "2026-11-15T13:00:00.000Z", payload };
}

const reading = (node: string, ind: string, extra = {}) => item("reading", { node, ind, ...extra });

function arrival(items: ReturnType<typeof item>[], beacon: Beacon | null = null): Arrival {
  return { arrival_id: 1, received_at: "2026-11-15T13:00:00.000Z", beacon, items };
}

const BEACON = { hold_s: 12 } as Beacon;
const spots = (a: Arrival) => [...spotsFor(a)].sort();

describe("spotsFor", () => {
  it("maps each bench node to its box", () => {
    expect(spots(arrival([reading("cabin-1", "cabin_temp")]))).toEqual(["cabin"]);
    expect(spots(arrival([reading("exercise-1", "load_raw")]))).toEqual(["cabin"]);
    expect(spots(arrival([reading("tilt-1", "tilt")]))).toEqual(["tilt"]);
    expect(spots(arrival([reading("ring-1", "hr")]))).toEqual(["ring"]);
  });

  it("lights the camera for a camera rep and the UNO for a load-cell rep", () => {
    expect(spots(arrival([item("rep", { node: "camera", src: "camera" })]))).toEqual(["camera"]);
    expect(spots(arrival([item("rep", { node: "exercise-1", src: "load_cell" })]))).toEqual(["cabin"]);
  });

  it("lights the hub for its own beacon, alerts, derived readings and console entries", () => {
    expect(spots(arrival([], BEACON))).toEqual(["hub"]);
    expect(spots(arrival([item("alert", { ind: "cabin_temp" })]))).toEqual(["hub"]);
    expect(spots(arrival([reading("sim-1", "cabin_ppco2", { derived_from: 7 })]))).toEqual(["hub"]);
    expect(spots(arrival([reading("manual", "bp_sys")]))).toEqual(["hub"]);
    expect(spots(arrival([item("prompt_answer", { node: "manual" })]))).toEqual(["hub"]);
  });

  it("maps synthetic sim-1 readings by indicator", () => {
    expect(spots(arrival([reading("sim-1", "cabin_temp"), reading("sim-1", "cabin_rh")]))).toEqual(["cabin"]);
    expect(spots(arrival([reading("sim-1", "hr"), reading("sim-1", "spo2"), reading("sim-1", "sleep_h")])))
      .toEqual(["ring"]);
    expect(spots(arrival([reading("sim-1", "tilt")]))).toEqual(["tilt"]);
  });

  it("lights nothing for readings no part on the bench makes", () => {
    expect(spots(arrival([reading("sim-1", "cabin_co2"), reading("sim-1", "skin_temp")]))).toEqual([]);
    expect(spots(arrival([reading("vitals-1", "hr")]))).toEqual([]);
  });

  it("collects every box an arrival touches", () => {
    expect(spots(arrival([reading("cabin-1", "cabin_rh"), reading("ring-1", "hr")], BEACON)))
      .toEqual(["cabin", "hub", "ring"]);
  });
});

describe("flash", () => {
  const a = arrival([reading("cabin-1", "cabin_temp")]);

  it("lights a box for FLASH_MS after its data arrives", () => {
    const lit = noteArrival(emptyLit(), a, 10000);
    expect([...litSpots(lit, 10000)]).toEqual(["cabin"]);
    expect([...litSpots(lit, 10000 + FLASH_MS - 1)]).toEqual(["cabin"]);
    expect([...litSpots(lit, 10000 + FLASH_MS)]).toEqual([]);
  });

  it("does not light a box for data that has not arrived yet", () => {
    expect([...litSpots(noteArrival(emptyLit(), a, 10000), 9999)]).toEqual([]);
  });

  it("starts with nothing lit", () => {
    expect([...litSpots(emptyLit(), 0)]).toEqual([]);
  });

  it("leaves the earlier state untouched", () => {
    const before = emptyLit();
    noteArrival(before, a, 10000);
    expect([...litSpots(before, 10000)]).toEqual([]);
  });
});

describe("spotsInFile", () => {
  it("lists the boxes that have any data in a replay", () => {
    const file = {
      arrivals: [
        { at_ms: 0, beacon: BEACON, items: [] },
        { at_ms: 1, beacon: null, items: [reading("sim-1", "hr"), reading("sim-1", "cabin_temp")] },
      ],
    } as unknown as ReplayFile;
    expect([...spotsInFile(file)].sort()).toEqual(["cabin", "hub", "ring"]);
  });
});
