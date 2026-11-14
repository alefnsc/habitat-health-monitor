import { describe, expect, it } from "vitest";
import { G_ENV_MS2 } from "@ground-truth/physics";
import { analyzeSession, type PoseFrame, type SessionResult } from "../src/index";
import { lcg, syntheticSession } from "./helpers";

// analyzeSession takes whatever an adapter produces. Bad DATA is refused with reasons and never
// thrown on; only invalid OPTIONS (a negative mass, a cutoff of zero) are programmer errors. A cutoff the
// stream's frame rate cannot carry is a property of the stream, and is refused.

const SCALE = 2.5;
const OPTIONS = { massKg: 10, gEnvMs2: G_ENV_MS2.EARTH, metersPerUnit: SCALE };
const session = (over: Partial<Parameters<typeof syntheticSession>[0]> = {}): PoseFrame[] =>
  syntheticSession({ reps: 3, heightM: 0.5, upS: 1, downS: 1, restS: 0.5, rateHz: 60, noiseM: 0.002, seed: 1, metersPerUnit: SCALE, ...over });

function ok(r: SessionResult) {
  if (!r.ok) throw new Error(`expected a measurement, got a refusal: ${r.reasons.join(", ")}`);
  return r;
}

describe("analyzeSession: bad data is refused, not thrown on", () => {
  it("a frame processed twice: the duplicate is dropped, counted, and the session still measures 3 reps", () => {
    const f = session();
    const doubled = f.flatMap((x, i) => (i % 40 === 5 ? [x, { ...x }] : [x]));
    const r = ok(analyzeSession(doubled, OPTIONS));
    expect(r.quality.droppedFrames).toBe(f.filter((_, i) => i % 40 === 5).length);
    expect(r.reps).toHaveLength(3);
  });

  it("a stream of mostly repeated timestamps is refused with LANDMARK_LOST", () => {
    const f = session();
    const doubled = f.flatMap((x, i) => (i % 3 === 0 ? [x, { ...x }] : [x]));
    const r = analyzeSession(doubled, OPTIONS);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["LANDMARK_LOST"]);
  });

  it("an out-of-order frame does not throw", () => {
    const f = session();
    const r = ok(analyzeSession([...f.slice(0, 100), f[40]!, ...f.slice(100)], OPTIONS));
    expect(r.quality.droppedFrames).toBe(1);
    expect(r.reps).toHaveLength(3);
  });

  it("a recording too short for the filter's padding is refused with TOO_SHORT: 1.2 s with a 2 Hz cutoff", () => {
    const f = session({ reps: 0, restS: 1.2 });
    const r = analyzeSession(f, { ...OPTIONS, cutoffHz: 2 });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toEqual(["TOO_SHORT"]);
    expect(r.quality.reasons).toEqual(["TOO_SHORT"]);
    expect(r.quality.durationS).toBeGreaterThan(1);
  });

  it("the same 1.2 s recording is long enough for the default 4 Hz cutoff (73 samples, padding 45): no TOO_SHORT, only NO_REPS for holding still", () => {
    const r = analyzeSession(session({ reps: 0, restS: 1.2 }), OPTIONS);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reasons).toEqual(["NO_REPS"]);
  });

  it("timestamps in milliseconds do not throw (they are refused, and that is fine)", () => {
    const ms = session().map((x) => ({ ...x, tS: x.tS * 1000 }));
    expect(() => analyzeSession(ms, OPTIONS)).not.toThrow();
    expect(analyzeSession(ms, OPTIONS).ok).toBe(false);
  });

  it("timestamps whose median spacing is far tighter than the stream's overall spacing are refused, not resampled into millions of samples", () => {
    let t = 0;
    const frames: PoseFrame[] = Array.from({ length: 3000 }, (_, i) => {
      t += i < 1700 ? 1e-6 : 0.2;
      return { tS: t, wristY: 0.5, visibility: 1 };
    });
    const r = analyzeSession(frames, OPTIONS);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reasons).toContain("LOW_FRAME_RATE");
  });

  it("empty, single-frame and all-identical-timestamp input do not throw", () => {
    const f = session();
    for (const frames of [[], [f[0]!], f.map((x) => ({ ...x, tS: 5 }))]) {
      expect(() => analyzeSession(frames, OPTIONS)).not.toThrow();
      expect(analyzeSession(frames, OPTIONS).ok).toBe(false);
    }
  });

  it("200 sessions with seeded garbage in tS, wristY and visibility never throw", () => {
    const garbageT = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1, 0, 1e308, 1e-300];
    const garbageY = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, 1e308, -1e308, 1e6, -7];
    const garbageV = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1, 2, 0, 0.4999];
    const pick = <T,>(xs: readonly T[], r: () => number): T => xs[Math.floor((r() + 1) * 0.5 * xs.length)] as T;
    for (let seed = 1; seed <= 200; seed++) {
      const r = lcg(seed);
      const corruptP = seed % 2 === 0 ? 0.2 : 0.02; // chance of corrupting a frame
      const frames = session({ seed }).map((f) => {
        if ((r() + 1) * 0.5 > corruptP) return f;
        const kind = Math.floor((r() + 1) * 1.5);
        return kind === 0 ? { ...f, tS: pick(garbageT, r) } : kind === 1 ? { ...f, wristY: pick(garbageY, r) } : { ...f, visibility: pick(garbageV, r) };
      });
      expect(() => analyzeSession(frames, OPTIONS), `seed ${seed}`).not.toThrow();
    }
  });

  it("still throws a RangeError for invalid OPTIONS", () => {
    const f = session();
    expect(() => analyzeSession(f, { ...OPTIONS, massKg: -1 })).toThrow(RangeError);
    expect(() => analyzeSession(f, { ...OPTIONS, cutoffHz: 0 })).toThrow(/cutoffHz/);
    expect(() => analyzeSession(f, { ...OPTIONS, cutoffHz: Number.NaN })).toThrow(/cutoffHz/);
  });

  // Whether a cutoff is below the Nyquist frequency depends on the STREAM's frame rate, which is frame
  // content: cutoffHz 12 is fine at 30 fps and impossible at 23.976 fps. It is refused, never thrown on.
  it("a cutoff at or above the stream's Nyquist frequency is refused with LOW_FRAME_RATE: 12 Hz at 23.976 fps, accepted at 30 fps", () => {
    const film = analyzeSession(session({ rateHz: 23.976 }), { ...OPTIONS, cutoffHz: 12 });
    expect(film.ok).toBe(false);
    if (film.ok) return;
    expect(film.reasons).toEqual(["LOW_FRAME_RATE"]);
    expect(film.quality.reasons).toEqual(["LOW_FRAME_RATE"]);
    expect(film.quality.rateHz).toBeCloseTo(23.976, 3);
    expect(ok(analyzeSession(session({ rateHz: 30 }), { ...OPTIONS, cutoffHz: 12 })).reps).toHaveLength(3);
    // under Nyquist is accepted, over it is not (60 fps: 30 Hz)
    expect(analyzeSession(session(), { ...OPTIONS, cutoffHz: 29 }).ok).toBe(true);
    expect(analyzeSession(session(), { ...OPTIONS, cutoffHz: 31 }).ok).toBe(false);
  });

  it("the Nyquist refusal joins the other reasons, in their usual order, and is not repeated", () => {
    const noScale = analyzeSession(session(), { ...OPTIONS, metersPerUnit: null, cutoffHz: 40 });
    expect(noScale.ok).toBe(false);
    if (!noScale.ok) expect(noScale.reasons).toEqual(["NO_SCALE", "LOW_FRAME_RATE"]);
    const slow = analyzeSession(session({ rateHz: 15 }), { ...OPTIONS, cutoffHz: 10 });
    expect(slow.ok).toBe(false);
    if (!slow.ok) expect(slow.reasons).toEqual(["LOW_FRAME_RATE"]);
    const lost = analyzeSession(session().map((f, i) => (i >= 100 && i < 130 ? { ...f, visibility: 0.1 } : f)), { ...OPTIONS, cutoffHz: 40 });
    expect(lost.ok).toBe(false);
    if (!lost.ok) expect(lost.reasons).toEqual(["LOW_FRAME_RATE", "GAP_TOO_LONG"]);
  });
});
