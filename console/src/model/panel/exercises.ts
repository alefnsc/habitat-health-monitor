import type { Exercise, Session } from "../../contract";

export const EXERCISES: Exercise[] = ["curl", "overhead_press", "row"];

/** Exercises with at least one recorded rep, from sets started in the 24 hours before `nowMs`, in checklist order. */
export function exercisesDone(sessions: Session[], nowMs: number): Exercise[] {
  const since = nowMs - 24 * 3600 * 1000;
  const done = new Set(
    sessions.filter((s) => s.exercise && s.camera_reps + s.load_cell_reps > 0 && Date.parse(s.started_at) >= since && Date.parse(s.started_at) <= nowMs)
      .map((s) => s.exercise as Exercise),
  );
  return EXERCISES.filter((e) => done.has(e));
}
