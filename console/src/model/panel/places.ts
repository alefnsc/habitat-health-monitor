// Same lift, four places: the rep's work estimate rescaled by each place's surface gravity (W = m * g * h).
export type PlaceKey = "earth" | "moon" | "mars" | "iss";

// Moon and Mars: NASA NSSDC fact sheets (surface gravity). Earth: standard gravity, as the camera uses.
// Space station: free fall, about 0 g (NASA Glenn, Physical Sciences Program).
export const PLACES: { key: PlaceKey; g: number }[] = [
  { key: "earth", g: 9.81 },
  { key: "moon", g: 1.62 },
  { key: "mars", g: 3.73 },
  { key: "iss", g: 0 },
];

export interface PlaceWork {
  key: PlaceKey;
  g: number;
  j: number;
}

const ok = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

export function placesWork(rep: { work_j: number; g: number } | null): PlaceWork[] | null {
  if (!rep || !ok(rep.work_j) || !ok(rep.g) || rep.g <= 0) return null;
  return PLACES.map((p) => ({ key: p.key, g: p.g, j: (rep.work_j * p.g) / rep.g }));
}
