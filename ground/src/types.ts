export type LinkStateName = "contact" | "blackout" | "unreachable";
export type BlackoutCause = "scheduled" | "unreachable";

export interface LastBlackout {
  start: string;
  end: string | null;
}

export interface LinkState {
  state: LinkStateName;
  light_time_s: number;
  time_scale: number;
  queue_len: number;
  last_blackout: LastBlackout | null;
}

export interface Beacon {
  link: LinkState;
  hold_s: number;
  in_flight: number;
  fetched_id: number;
  delivered_id: number;
  last_blackout_cause: BlackoutCause | null;
  sent_at: string;
}

export type ItemKind = "reading" | "rep" | "alert" | "prompt_answer";

export interface OutboxItem {
  id: number;
  kind: ItemKind;
  created_at: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: Record<string, any>;
}

export interface Arrival {
  arrival_id: number;
  received_at: string;
  beacon: Beacon | null;
  items: OutboxItem[];
}

export type Status = "ok" | "watch" | "act" | "unknown";

export interface LatestEntry {
  ind: string;
  val: number;
  unit: string;
  status: Status;
  rule_id: string | null;
  src: string;
  source_kind: string | null;
  measured_at: string;
  crew: string | null;
  /** Node that made the reading; sim-1 is synthetic. */
  node: string | null;
  greyed: boolean;
}

export interface AlertEntry {
  id: string | number;
  ind: string;
  status: Status;
  prev_status: Status;
  rule_id: string | null;
  measured_at: string;
  crew: string | null;
  escalate_to: string | null;
}

export interface GroundView {
  beacon: Beacon | null;
  lastArrivalMs: number | null;
  received: number;
  latest: Map<string, LatestEntry>;
  alerts: AlertEntry[];
  seen: Set<number>;
}

export interface ReplayArrival {
  at_ms: number;
  beacon: Beacon | null;
  items: OutboxItem[];
}

export interface ReplayFile {
  v: number;
  kind: "ground-replay";
  label: string;
  exported_at: string;
  t0: string;
  light_time_s: number;
  time_scale: number;
  arrivals: ReplayArrival[];
}
