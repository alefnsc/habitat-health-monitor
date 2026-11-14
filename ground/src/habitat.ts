import type { Arrival, OutboxItem, ReplayFile } from "./types";

/** The boxes on the habitat map. */
export type Spot = "cabin" | "camera" | "tilt" | "hub" | "ring";

export const FLASH_MS = 600;

/** Bench nodes (D40/D41). cabin-1 and exercise-1 are both the UNO I/O board. */
const NODE_SPOT: Record<string, Spot> = {
  "cabin-1": "cabin",
  "exercise-1": "cabin",
  "tilt-1": "tilt",
  camera: "camera",
  "ring-1": "ring",
  // Made by the hub itself: console entries, food log, NASA fetches.
  manual: "hub",
  food: "hub",
  nasa: "hub",
};

/** Synthetic sim-1 readings, mapped to the box that makes that reading on the bench. */
const SIM_SPOT: Record<string, Spot> = {
  cabin_temp: "cabin",
  cabin_rh: "cabin",
  hr: "ring",
  spo2: "ring",
  sleep_h: "ring",
  tilt: "tilt",
};

function spotForItem(item: OutboxItem): Spot | null {
  const p = item.payload;
  switch (item.kind) {
    case "alert":
    case "prompt_answer":
      return "hub";
    case "rep":
      return p.src === "camera" ? "camera" : p.src === "load_cell" ? "cabin" : null;
    case "reading":
      if (p.derived_from !== null && p.derived_from !== undefined) return "hub";
      if (p.node === "sim-1") return SIM_SPOT[p.ind] ?? null;
      return NODE_SPOT[p.node] ?? null;
    default:
      return null;
  }
}

/** Boxes an arrival touches: the hub for its beacon, plus the box of each item. */
export function spotsFor(arrival: Arrival): Set<Spot> {
  const out = new Set<Spot>();
  if (arrival.beacon) out.add("hub");
  for (const item of arrival.items) {
    const s = spotForItem(item);
    if (s) out.add(s);
  }
  return out;
}

/** Ground-clock time each box last received data, or absent. */
export type Lit = Partial<Record<Spot, number>>;

export function emptyLit(): Lit {
  return {};
}

export function noteArrival(lit: Lit, arrival: Arrival, atMs: number): Lit {
  const next = { ...lit };
  for (const s of spotsFor(arrival)) next[s] = atMs;
  return next;
}

export function litSpots(lit: Lit, nowMs: number): Set<Spot> {
  const out = new Set<Spot>();
  for (const [s, at] of Object.entries(lit) as [Spot, number][]) {
    if (nowMs >= at && nowMs - at < FLASH_MS) out.add(s);
  }
  return out;
}

/** Boxes that get any data anywhere in a replay file. */
export function spotsInFile(file: ReplayFile): Set<Spot> {
  const out = new Set<Spot>();
  for (const a of file.arrivals) {
    for (const s of spotsFor({ arrival_id: 0, received_at: "", beacon: a.beacon, items: a.items })) out.add(s);
  }
  return out;
}
