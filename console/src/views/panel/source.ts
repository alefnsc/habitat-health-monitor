import {
  getExerciseDay, getFoodDay, getIssCabin, getIssReference, getLink, getReadings, getReps, getSessions, getSpaceWeather,
  getSignals, getStatus,
} from "../../api";
import type {
  CrewId, ExerciseDay, FoodDay, Ind, IssCabin, IssReference, LinkState, RepsBody, Session, SignalsBody, SpaceWeather,
  StatusBody, StoredReading,
} from "../../contract";
import { COPY } from "../../copy";

/**
 * Where the habitat panel reads from: the hub over HTTP, or a recorded replay. The cards are the same in both; a
 * feed the source does not carry rejects, and its card shows that it has no data.
 */
export interface PanelSource {
  /** Where the values come from when not from a live hub, shown next to them: "Replay (recorded)". */
  label?: string;
  /** Where the lift cards' set comes from, when the source has to say so. */
  setNote?: string;
  /** The source's own wording, by copy key, where the live wording would point at a hub. */
  text?: Readonly<Record<string, string>>;
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
  /** D45 signals. A source without it (the recorded replay) shows no signals chip. */
  signals?(crew?: CrewId): Promise<SignalsBody>;
}

/** What a card needs to know about its source: its clock, its label and its wording. */
export type CardSource = Pick<PanelSource, "now" | "label" | "setNote" | "text">;

/** The card text for `key`: the source's own wording if it has one, else the console's. */
export const copyFor = (src: Pick<PanelSource, "text">, key: string): string => src.text?.[key] ?? COPY[key];

export const liveSource: PanelSource = {
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
  signals: (crew) => getSignals(crew),
};
