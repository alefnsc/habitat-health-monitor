import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError, endSession, framesForSet, postRep, postRepsWithRetry, startSession, unloadGuard, type PostResult } from "../src/session";
import { wristSample } from "../../vendor/ground-truth/demo/src/pose/landmarks";
import type { RepMessage } from "../src/reps";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const SESSION = { session: "s-1794657600000", mass_kg: 10, g: 9.81, crew: "crew-a", started_at: "x", ended_at: null, camera_reps: 0, load_cell_reps: 0 };
const msg = (seq: number): RepMessage => ({
  v: 1, node: "camera", boot: 1, seq, age_ms: 0, type: "rep", session: "s", rep: seq, src: "camera", peak_n: 1, work_j: 1,
  rom_m: 0.5, g: 9.81, mass_kg: 10, t0_ms: 0, t1_ms: 1000, work_ecc_j: 0, t_con_ms: 500, t_ecc_ms: 500, t_turn_ms: 500,
});
const res = (dup = false): PostResult => ({ id: 1, measured_at: "x", duplicate: dup, results: [] });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("session", () => {
  test("test_start_session", async () => {
    const f = vi.fn().mockResolvedValue(json(SESSION, 201));
    const s = await startSession({ mass_kg: 10, g: 9.81, crew: "crew-a" }, f as unknown as typeof fetch);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("/api/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ mass_kg: 10, g: 9.81, crew: "crew-a" });
    expect("session" in JSON.parse(init.body)).toBe(false);
    expect(s).toMatchObject({ session: "s-1794657600000", ended_at: null, camera_reps: 0, load_cell_reps: 0 });
  });

  test("test_end_session", async () => {
    const f = vi.fn().mockResolvedValue(json({ ...SESSION, ended_at: "2026-11-14T12:00:00Z" }));
    const s = await endSession("s-1794657600000", f as unknown as typeof fetch);
    expect(f.mock.calls[0][0]).toBe("/api/sessions/s-1794657600000/end");
    expect(s.ended_at).not.toBeNull();
  });

  test("postRep posts the message", async () => {
    const f = vi.fn().mockResolvedValue(json({ id: 1, measured_at: "x", duplicate: false, results: [] }, 201));
    await postRep(msg(1), f as unknown as typeof fetch);
    expect(f.mock.calls[0][0]).toBe("/api/reps");
  });

  test("test_retry_then_success", async () => {
    const seen: number[] = [];
    let n = 0;
    const post = async (m: RepMessage) => {
      seen.push(m.seq);
      if (++n <= 2) throw new ApiError(0, "timeout");
      return res();
    };
    const p = postRepsWithRetry([msg(1)], post, { intervalMs: 2000, maxTries: 15 });
    await vi.advanceTimersByTimeAsync(4000);
    expect(await p).toEqual({ sent: 1, pending: 0, rejected: [] });
    expect(seen).toEqual([1, 1, 1]);
  });

  test("test_age_is_recomputed_per_attempt", async () => {
    const t0 = performance.now() - 1000; // the rep ended (t1_ms = 1000) as the test starts
    const age = (m: RepMessage) => Math.max(0, Math.round(performance.now() - (t0 + m.t1_ms)));
    const sentAges: { seq: number; age: number }[] = [];
    let n = 0;
    const post = async (m: RepMessage) => {
      sentAges.push({ seq: m.seq, age: m.age_ms });
      if (++n === 1) throw new ApiError(0, "timeout");
      return res();
    };
    const p = postRepsWithRetry([msg(1), msg(2)], post, { intervalMs: 2000, maxTries: 15, age });
    await vi.advanceTimersByTimeAsync(4000);
    expect(await p).toEqual({ sent: 2, pending: 0, rejected: [] });
    // First attempt at +0 ms, retry after the 2 s sleep, second rep sent right after that.
    expect(sentAges).toEqual([{ seq: 1, age: 0 }, { seq: 1, age: 2000 }, { seq: 2, age: 2000 }]);
  });

  test("test_duplicate_is_sent", async () => {
    const post = vi.fn().mockResolvedValue(res(true));
    const r = await postRepsWithRetry([msg(1)], post, { intervalMs: 2000, maxTries: 15 });
    expect(r.sent).toBe(1);
    expect(post).toHaveBeenCalledTimes(1);
  });

  test("test_no_retry_on_422", async () => {
    const post = vi.fn().mockRejectedValue(new ApiError(422, "HTTP 422: bad_value:t1_ms"));
    const r = await postRepsWithRetry([msg(3)], post, { intervalMs: 2000, maxTries: 15 });
    expect(post).toHaveBeenCalledTimes(1);
    expect(r.rejected).toEqual([{ seq: 3, reason: "HTTP 422: bad_value:t1_ms" }]);
  });

  test("test_gives_up", async () => {
    const post = vi.fn().mockRejectedValue(new ApiError(0, "timeout"));
    const p = postRepsWithRetry([msg(1)], post, { intervalMs: 2000, maxTries: 15 });
    await vi.advanceTimersByTimeAsync(30000);
    expect(await p).toEqual({ sent: 0, pending: 1, rejected: [] });
    expect(post).toHaveBeenCalledTimes(15);
  });

  test("test_unload_warning", () => {
    const e = { preventDefault: vi.fn(), returnValue: "" as unknown };
    unloadGuard(() => 1)(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(e.returnValue).toBe("Some reps have not been sent yet.");
    const e2 = { preventDefault: vi.fn(), returnValue: "" as unknown };
    unloadGuard(() => 0)(e2);
    expect(e2.preventDefault).not.toHaveBeenCalled();
  });

  test("test_side_choice", () => {
    const lm = (side: "L" | "R" | "B") =>
      Array.from({ length: 33 }, (_, i) => ({ x: 0.5, y: i === 15 ? 0.3 : i === 16 ? 0.7 : 0.5, z: 0, visibility: (i === 15 && side !== "R") || (i === 16 && side !== "L") ? 1 : 0 }));
    const samples = Array.from({ length: 10 }, (_, i) => wristSample(i / 30, i < 9 ? lm("B") : lm("L")));
    // right wrist visible only in 2 of 10 frames, left in all
    const s2 = samples.map((s, i) => (i < 8 ? wristSample(i / 30, lm("L")) : wristSample(i / 30, lm("B"))));
    const r = framesForSet(s2);
    expect(r.side).toBe("LEFT");
    expect(r.frames.map((f) => f.wristY)).toEqual(s2.map((s) => s.LEFT.wristY));
  });
});
