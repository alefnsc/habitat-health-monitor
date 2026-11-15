import {
  getExerciseDay, getFoodDay, getIssCabin, getIssReference, getLink, getReadings, getReps, getSessions, getSpaceWeather,
  getStatus,
} from "../../api";
import type {
  CrewId, ExerciseDay, FoodDay, Ind, IssCabin, IssReference, LinkState, RepsBody, Session, SpaceWeather, StatusBody,
  StoredReading,
} from "../../contract";

/**
 * Where the habitat panel reads from: the hub over HTTP, or a recorded replay. The cards are the same in both; a
 * feed the source does not carry rejects, and its card shows that it has no data.
 */
export interface PanelSource {
  /** True when every value comes from a recorded replay file, never from a hub. */
  replay: boolean;
  /** Milliseconds since the epoch: the wall clock on a live hub, the replay clock in the replay. */
  now(): number;
  /** Overrides of the panel's refresh times and of its 6-hour lane window (seconds, for a clock of `nowS`). */
  refreshMs?: number;
  lanesRefreshMs?: number;
  laneWindow?(nowS: number): [number, number];
  status(crew?: CrewId): Promise<StatusBody>;
  sessions(): Promise<Session[]>;
  reps(session: string): Promise<RepsBody>;
  readings(ind: Ind, o: Parameters<typeof getReadings>[1]): Promise<StoredReading[]>;
  foodDay(crew?: CrewId): Promise<FoodDay>;
  exerciseDay(crew?: CrewId): Promise<ExerciseDay>;
  spaceWeather(): Promise<SpaceWeather>;
  issCabin(): Promise<IssCabin>;
  issReference(): Promise<IssReference>;
  link(): Promise<LinkState>;
}

/** What a card needs to know about its source: its clock, and whether it is a replay. */
export type PanelClock = Pick<PanelSource, "now" | "replay">;

export const liveSource: PanelSource = {
  replay: false,
  now: () => Date.now(),
  status: getStatus,
  sessions: getSessions,
  reps: getReps,
  readings: getReadings,
  foodDay: (crew) => getFoodDay(crew),
  exerciseDay: (crew) => getExerciseDay(crew),
  spaceWeather: getSpaceWeather,
  issCabin: getIssCabin,
  issReference: getIssReference,
  link: getLink,
};
