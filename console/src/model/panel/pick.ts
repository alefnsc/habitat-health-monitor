import type { CrewId, Session } from "../../contract";

/** The lift cards show the newest session that has camera reps: a set still recording, or one the camera refused,
 *  has none yet, and must not hide the last good set. Falls back to the newest session. Input is newest first. */
export const pickSession = (sessions: readonly Session[]): Session | null =>
  sessions.find((s) => s.camera_reps > 0) ?? sessions[0] ?? null;

/** Cabin readings carry no crew (hub CABIN_INDS are all cabin_*), so only body lanes follow the crew selector. */
export const laneCrew = (ind: string, crew: CrewId | undefined): CrewId | undefined =>
  ind.startsWith("cabin_") ? undefined : crew;
