import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  ApiError, buildUrl, getExerciseDay, getFoodCatalog, getFoodDay, getFoodReferences, getPrompts, getStatus,
  postFoodLog, postReading,
} from "../src/api";
import type { ReadingMessage } from "../src/contract";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const urlOf = (i = 0) => fetchMock.mock.calls[i][0] as string;
const MSG: ReadingMessage = {
  v: 1, node: "manual", boot: 1, seq: 1, age_ms: 0, ind: "hr", val: 60, unit: "bpm", src: "certified", dev: "manual",
  q: ["ok"], crew: "crew-a",
};

describe("api", () => {
  test("test_build_url", () => {
    expect(buildUrl("/api/readings", { ind: "hr", since: undefined, limit: 100 })).toBe("/api/readings?ind=hr&limit=100");
    expect(buildUrl("/api/readings", { since: "2026-11-14T12:00:00Z" })).toBe(
      "/api/readings?since=2026-11-14T12%3A00%3A00Z",
    );
  });

  test("test_get_status_crew", async () => {
    fetchMock.mockImplementation(async () => json({ crew: null, generated_at: "x", nodes: [], results: [] }));
    await getStatus("crew-b");
    expect(urlOf(0)).toBe("/api/status?crew=crew-b");
    await getStatus();
    expect(urlOf(1)).toBe("/api/status");
  });

  test("test_get_status_body", async () => {
    const body = { crew: null, generated_at: "2026-11-14T12:00:00.000Z", nodes: [], results: [{ ind: "hr" }] };
    fetchMock.mockResolvedValueOnce(json(body));
    await expect(getStatus()).resolves.toEqual(body);
    fetchMock.mockResolvedValueOnce(json([]));
    await expect(getStatus()).rejects.toMatchObject({ status: 0, message: "unexpected response from /api/status" });
  });

  test("test_post_reading", async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 1, measured_at: "x", duplicate: false, results: [] }, 201));
    await postReading(MSG);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/readings");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.body).toBe(JSON.stringify(MSG));
  });

  test("test_post_duplicate_is_sent", async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 7, measured_at: "x", duplicate: true, results: [] }, 200));
    await expect(postReading(MSG)).resolves.toMatchObject({ duplicate: true });
    fetchMock.mockResolvedValueOnce(json({ id: 8, measured_at: "x", duplicate: false, results: [] }, 201));
    await expect(postReading(MSG)).resolves.toMatchObject({ duplicate: false });
  });

  test("test_http_error", async () => {
    fetchMock.mockResolvedValueOnce(json({ error: "contract", reason: "unit_mismatch" }, 422));
    await expect(postReading(MSG)).rejects.toMatchObject({ status: 422, message: "HTTP 422: unit_mismatch" });
    fetchMock.mockResolvedValueOnce(new Response("", { status: 500 }));
    await expect(postReading(MSG)).rejects.toMatchObject({ status: 500, message: "HTTP 500" });
    expect(new ApiError(1, "x")).toBeInstanceOf(Error);
  });

  test("test_timeout", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => new Promise(() => {}));
    const p = getStatus();
    const assertion = expect(p).rejects.toMatchObject({ status: 0, message: "timeout" });
    await vi.advanceTimersByTimeAsync(5000);
    await assertion;
  });

  test("test_prompts_url", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await getPrompts();
    await getPrompts("crew-a");
    await getPrompts("crew-a", "all");
    await getPrompts(undefined, "open");
    expect([0, 1, 2, 3].map(urlOf)).toEqual([
      "/api/prompts", "/api/prompts?crew=crew-a", "/api/prompts?crew=crew-a&status=all", "/api/prompts?status=open",
    ]);
  });

  test("test_food_urls", async () => {
    fetchMock.mockImplementation(async () =>
      json({ totals: {}, items: [], sessions: 0 }),
    );
    await getFoodDay("crew-b", "2026-11-15T12:00:00.000Z");
    await getFoodDay();
    await getExerciseDay("crew-b", "2026-11-15T12:00:00.000Z");
    await getFoodCatalog();
    await getFoodReferences();
    expect([0, 1, 2, 3, 4].map(urlOf)).toEqual([
      "/api/food/day?crew=crew-b&at=2026-11-15T12%3A00%3A00.000Z",
      "/api/food/day",
      "/api/exercise/day?crew=crew-b&at=2026-11-15T12%3A00%3A00.000Z",
      "/api/food/catalog",
      "/api/food/references",
    ]);
  });

  test("test_post_food_log", async () => {
    const req = { crew: "crew-a" as const, items: [{ food_id: "fx-bar", servings: 2 }] };
    fetchMock.mockResolvedValueOnce(json({ meal_id: 3, readings: [], not_reported: [], results: [] }, 201));
    await expect(postFoodLog(req)).resolves.toMatchObject({ meal_id: 3 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/food/log");
    expect(init.body).toBe(JSON.stringify(req));
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    fetchMock.mockResolvedValueOnce(json({ reason: "empty_meal" }, 422));
    await expect(postFoodLog(req)).rejects.toMatchObject({ status: 422, message: "HTTP 422: empty_meal" });
    fetchMock.mockResolvedValueOnce(new Response("", { status: 404 }));
    await expect(postFoodLog(req)).rejects.toMatchObject({ message: "HTTP 404" });
  });

  test("test_food_guards", async () => {
    fetchMock.mockResolvedValueOnce(json({ crew: null }));
    await expect(getFoodDay()).rejects.toMatchObject({ message: "unexpected response from /api/food/day" });
    fetchMock.mockResolvedValueOnce(json({ version: 1 }));
    await expect(getFoodCatalog()).rejects.toMatchObject({ message: "unexpected response from /api/food/catalog" });
  });
});
