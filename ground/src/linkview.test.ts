import { describe, expect, it } from "vitest";
import { linkFrame, linkSchedule, liveLinkFrame } from "./linkview";
import type { Beacon, ReplayArrival, ReplayFile } from "./types";

const T0 = Date.parse("2026-11-15T13:00:00.000Z");
const iso = (ms: number) => new Date(T0 + ms).toISOString();

function beacon(last: { start: number; end: number | null } | null = null): Beacon {
  return {
    link: {
      state: "contact", light_time_s: 720, time_scale: 60, queue_len: 0,
      last_blackout: last ? { start: iso(last.start), end: last.end === null ? null : iso(last.end) } : null,
    },
    hold_s: 12, in_flight: 0, fetched_id: 0, delivered_id: 0,
    last_blackout_cause: last ? "scheduled" : null, sent_at: iso(0),
  };
}

const items = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: i, kind: "reading" as const, created_at: iso(0), payload: {} }));

function file(arrivals: ReplayArrival[]): ReplayFile {
  return {
    v: 1, kind: "ground-replay", label: "test", exported_at: "z", t0: iso(0),
    light_time_s: 720, time_scale: 60, arrivals,
  };
}

// Link down at Mars from 30 s to 60 s; beacons after it report the blackout (twice).
const FILE = file([
  { at_ms: 0, beacon: beacon(), items: [] },
  { at_ms: 1000, beacon: null, items: items(3) },
  { at_ms: 5000, beacon: null, items: items(200) },
  { at_ms: 20000, beacon: beacon(), items: [] },
  { at_ms: 72500, beacon: beacon({ start: 30000, end: 60000 }), items: items(400) },
  { at_ms: 73500, beacon: beacon({ start: 30000, end: 60000 }), items: [] },
]);

describe("linkSchedule", () => {
  it("takes the hold and light-time from the beacon", () => {
    const s = linkSchedule(FILE);
    expect(s.holdMs).toBe(12000);
    expect(s.lightTimeS).toBe(720);
    expect(s.timeScale).toBe(60);
  });

  it("falls back to light_time / time_scale when no beacon exists", () => {
    const s = linkSchedule(file([{ at_ms: 0, beacon: null, items: [] }]));
    expect(s.holdMs).toBe(12000);
  });

  it("collects each blackout once, with its cause, in replay time", () => {
    expect(linkSchedule(FILE).blackouts).toEqual([{ startMs: 30000, endMs: 60000, cause: "scheduled" }]);
  });

  it("keeps a blackout with no end open, and closes it when a later beacon ends it", () => {
    const open = linkSchedule(file([{ at_ms: 0, beacon: beacon({ start: 30000, end: null }), items: [] }]));
    expect(open.blackouts[0].endMs).toBe(Infinity);
    const closed = linkSchedule(
      file([
        { at_ms: 0, beacon: beacon({ start: 30000, end: null }), items: [] },
        { at_ms: 1000, beacon: beacon({ start: 30000, end: 60000 }), items: [] },
      ]),
    );
    expect(closed.blackouts).toEqual([{ startMs: 30000, endMs: 60000, cause: "scheduled" }]);
  });
});

describe("linkFrame", () => {
  const s = linkSchedule(FILE);

  it("reports the one-way light-time in minutes and the demo hold", () => {
    const f = linkFrame(s, 0);
    expect(f.lightTimeMin).toBe(12);
    expect(f.holdS).toBe(12);
    expect(f.timeScale).toBe(60);
  });

  it("puts in flight exactly the arrivals due within one hold, positioned Mars 0 to Earth 1", () => {
    const f = linkFrame(s, 0);
    expect(f.packets.map((p) => p.x)).toEqual([1 - 1000 / 12000, 1 - 5000 / 12000]);
  });

  it("marks a packet carrying many items as big", () => {
    expect(linkFrame(s, 0).packets.map((p) => p.big)).toEqual([false, true]);
  });

  it("places a packet at Mars when it leaves and near Earth just before it lands", () => {
    expect(linkFrame(s, 20000 - 12000).packets.at(-1)!.x).toBe(0);
    expect(linkFrame(s, 19999).packets[0].x).toBeCloseTo(1, 3);
  });

  it("shows no blackout outside the blackout window", () => {
    const f = linkFrame(s, 10000);
    expect(f.gap).toBeNull();
    expect(f.marsDown).toBe(false);
    expect(f.earthDark).toBe(false);
    expect(f.cause).toBeNull();
  });

  it("grows the blackout gap from Mars once the link goes down", () => {
    const f = linkFrame(s, 36000);
    expect(f.gap).toEqual([0, 0.5]);
    expect(f.marsDown).toBe(true);
    expect(f.earthDark).toBe(false);
    expect(f.cause).toBe("scheduled");
  });

  it("fills the whole line while both ends are dark", () => {
    const f = linkFrame(s, 50000);
    expect(f.gap).toEqual([0, 1]);
    expect(f.marsDown).toBe(true);
    expect(f.earthDark).toBe(true);
  });

  it("drains the gap into Earth after the link is back at Mars", () => {
    const f = linkFrame(s, 66000);
    expect(f.gap).toEqual([0.5, 1]);
    expect(f.marsDown).toBe(false);
    expect(f.earthDark).toBe(true);
  });

  it("clears once the last blackout-time signal has reached Earth", () => {
    const f = linkFrame(s, 72000);
    expect(f.gap).toBeNull();
    expect(f.earthDark).toBe(false);
  });
});

describe("liveLinkFrame", () => {
  it("reads the light-time from the beacon and draws no packets", () => {
    const f = liveLinkFrame(beacon(), 1000, 1500);
    expect(f.lightTimeMin).toBe(12);
    expect(f.holdS).toBe(12);
    expect(f.packets).toEqual([]);
    expect(f.gap).toBeNull();
  });

  it("darkens Earth after more than 3 s of silence", () => {
    expect(liveLinkFrame(beacon(), 0, 3000).earthDark).toBe(false);
    expect(liveLinkFrame(beacon(), 0, 3001).earthDark).toBe(true);
  });

  it("has no light-time before the first beacon", () => {
    const f = liveLinkFrame(null, null, 0);
    expect(f.lightTimeMin).toBeNull();
    expect(f.earthDark).toBe(false);
  });
});
