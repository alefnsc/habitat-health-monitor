import { postCrew } from "./api";
import { COPY } from "./copy";
import type { CrewId } from "./contract";

export const CREW = [
  { id: "crew-a", label: COPY["crew.a"] },
  { id: "crew-b", label: COPY["crew.b"] },
  { id: "crew-c", label: COPY["crew.c"] },
] as const;

export const WEARER_NODES = ["vitals-1", "strap-1"] as const;
export type WearerNode = (typeof WEARER_NODES)[number];

const KEY = "habitat.crew";
const IDS: readonly string[] = CREW.map((c) => c.id);

export function loadCrew(storage: Storage | null): CrewId | null {
  try {
    const v = storage?.getItem(KEY);
    return v && IDS.includes(v) ? (v as CrewId) : null;
  } catch {
    return null;
  }
}

export function saveCrew(storage: Storage | null, id: CrewId | null): void {
  try {
    if (id === null) storage?.removeItem(KEY);
    else storage?.setItem(KEY, id);
  } catch {
    /* storage blocked: the page still works */
  }
}

function browserStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

let current: CrewId | null = loadCrew(browserStorage());
const subs = new Set<(id: CrewId | null) => void>();

export function currentCrew(): CrewId | null {
  return current;
}

export function setCurrentCrew(id: CrewId | null): void {
  if (id === current) return;
  current = id;
  saveCrew(browserStorage(), id);
  subs.forEach((cb) => cb(id));
}

export function onCrewChange(cb: (id: CrewId | null) => void): () => void {
  subs.add(cb);
  return () => subs.delete(cb);
}

export async function setWearer(
  node: WearerNode,
  crew: CrewId,
  post: typeof postCrew = postCrew,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await post(node, crew);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: `${COPY["crew.wearerError"]}${e instanceof Error ? e.message : String(e)}` };
  }
}
