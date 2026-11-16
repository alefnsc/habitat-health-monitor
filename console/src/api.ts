import type {
  CrewId, ExerciseDay, FoodCatalog, FoodDay, FoodReferences, Ind, IssCabin, IssReference, LinkState, MealRequest,
  MealResult, PostResult, Prompt, PromptAnswer, PromptAnswerResult, ReadingMessage, RepsBody, Session, SignalsBody,
  SpaceWeather, StatusBody, StoredReading,
} from "./contract";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TIMEOUT_MS = 5000;

type Params = Record<string, string | number | undefined>;

export function buildUrl(path: string, params: Params = {}): string {
  const q = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return q ? `${path}?${q}` : path;
}

async function request(method: "GET" | "POST", url: string, body?: unknown): Promise<unknown> {
  const ctl = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      ctl.abort();
      reject(new ApiError(0, "timeout"));
    }, TIMEOUT_MS);
  });
  const init: RequestInit = { method, signal: ctl.signal };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  try {
    const res = (await Promise.race([globalThis.fetch(url, init), timeout])) as Response;
    let json: unknown = null;
    try {
      json = await res.json();
    } catch {
      json = null;
    }
    if (!res.ok) {
      const reason =
        json && typeof json === "object" && typeof (json as { reason?: unknown }).reason === "string"
          ? `: ${(json as { reason: string }).reason}`
          : "";
      throw new ApiError(res.status, `HTTP ${res.status}${reason}`);
    }
    return json;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, e instanceof Error ? e.message : "network error");
  } finally {
    clearTimeout(timer);
  }
}

function guard<T>(path: string, json: unknown, ok: (o: Record<string, unknown>) => boolean): T {
  if (json && typeof json === "object" && !Array.isArray(json) && ok(json as Record<string, unknown>)) {
    return json as T;
  }
  throw new ApiError(0, `unexpected response from ${path}`);
}

const get = (path: string, params?: Params) => request("GET", buildUrl(path, params));
const post = (path: string, body: unknown) => request("POST", path, body);

export async function getStatus(crew?: CrewId): Promise<StatusBody> {
  return guard("/api/status", await get("/api/status", { crew }), (o) => Array.isArray(o.results));
}

export async function getReadings(
  ind: Ind,
  opts: { since?: string; limit?: number; crew?: CrewId; bucket_s?: number } = {},
): Promise<StoredReading[]> {
  const json = await get("/api/readings", { ind, since: opts.since, limit: opts.limit, crew: opts.crew, bucket_s: opts.bucket_s });
  if (!Array.isArray(json)) throw new ApiError(0, "unexpected response from /api/readings");
  return json as StoredReading[];
}

export async function postReading(msg: ReadingMessage): Promise<PostResult> {
  return guard("/api/readings", await post("/api/readings", msg), (o) => Array.isArray(o.results));
}

export async function postCrew(node: string, crew: CrewId): Promise<void> {
  await post("/api/crew", { node, crew });
}

export async function getSessions(): Promise<Session[]> {
  const json = await get("/api/sessions");
  if (!Array.isArray(json)) throw new ApiError(0, "unexpected response from /api/sessions");
  return json as Session[];
}

export async function getReps(session: string): Promise<RepsBody> {
  return guard("/api/reps", await get("/api/reps", { session }), (o) => Array.isArray(o.pairs));
}

export async function getSpaceWeather(): Promise<SpaceWeather> {
  return guard("/api/nasa/space-weather", await get("/api/nasa/space-weather"), (o) => typeof o.status === "string");
}

export async function ackSpaceWeather(crew: CrewId): Promise<void> {
  await post("/api/nasa/space-weather/ack", { crew });
}

export async function getIssCabin(): Promise<IssCabin> {
  return guard("/api/nasa/iss-cabin", await get("/api/nasa/iss-cabin"), (o) => Array.isArray(o.items));
}

export async function getIssReference(): Promise<IssReference> {
  return guard("/api/nasa/iss-reference", await get("/api/nasa/iss-reference"), (o) => typeof o.dose === "object");
}

export async function getPrompts(crew?: CrewId, status?: "open" | "all"): Promise<Prompt[]> {
  const json = await get("/api/prompts", { crew, status });
  if (!Array.isArray(json)) throw new ApiError(0, "unexpected response from /api/prompts");
  return json as Prompt[];
}

export async function answerPrompt(id: number, body: PromptAnswer): Promise<PromptAnswerResult> {
  return guard(`/api/prompts/${id}/answer`, await post(`/api/prompts/${id}/answer`, body), (o) =>
    Array.isArray(o.results),
  );
}

export async function getLink(): Promise<LinkState> {
  return guard("/api/link", await get("/api/link"), (o) => typeof o.state === "string");
}

export async function getFoodCatalog(): Promise<FoodCatalog> {
  return guard("/api/food/catalog", await get("/api/food/catalog"), (o) => Array.isArray(o.items));
}

export async function getFoodReferences(): Promise<FoodReferences> {
  return guard("/api/food/references", await get("/api/food/references"), (o) => Array.isArray(o.items));
}

export async function postFoodLog(req: MealRequest): Promise<MealResult> {
  return guard("/api/food/log", await post("/api/food/log", req), (o) => Array.isArray(o.results));
}

export async function getFoodDay(crew?: CrewId, at?: string): Promise<FoodDay> {
  return guard("/api/food/day", await get("/api/food/day", { crew, at }), (o) => typeof o.totals === "object" && o.totals !== null);
}

export async function getSignals(crew?: CrewId, at?: string): Promise<SignalsBody> {
  return guard("/api/signals", await get("/api/signals", { crew, at }), (o) => Array.isArray(o.signals));
}

export async function getExerciseDay(crew?: CrewId, at?: string): Promise<ExerciseDay> {
  return guard("/api/exercise/day", await get("/api/exercise/day", { crew, at }), (o) => typeof o.sessions === "number");
}
