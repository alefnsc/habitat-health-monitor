import type { CrewId } from "./session";

export interface Tap { x: number; y: number }

/** Calibration takes two taps; a third tap starts the pair over instead of being ignored. */
export const addTap = (taps: readonly Tap[], tap: Tap): Tap[] => (taps.length >= 2 ? [tap] : [...taps, tap]);

const CREWS: readonly CrewId[] = ["crew-a", "crew-b", "crew-c"];

/** No default pick: an empty or unknown value is no crew, so a forgotten choice cannot label the set. */
export const parseCrew = (v: string): CrewId | null => ((CREWS as readonly string[]).includes(v) ? (v as CrewId) : null);
