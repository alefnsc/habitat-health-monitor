import { describe, expect, test } from "vitest";
import { ackState, weatherBanner } from "../src/model/nasa";
import type { SpaceWeather } from "../src/contract";
import act from "./fixtures/nasa/space-weather-act.json";

const NOW = Date.parse("2026-11-14T12:00:00Z");
const sw = (o: Partial<SpaceWeather> = {}): SpaceWeather => ({ ...(act as unknown as SpaceWeather), ...o });
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

describe("space-weather banner", () => {
  test("test_ok_hidden", () => {
    const b = weatherBanner(sw({ status: "ok", stale: false, mode: "live", cached_at: ago(120), reason: "" }), NOW);
    expect(b.show).toBe(false);
    expect(b.cachedText).toBe("Space weather quiet, checked 2 min ago");
  });

  test("test_act", () => {
    const b = weatherBanner(sw({ status: "act", rule_id: "radiation_spe", reason: "SEP event", event_time: "2026-11-14T10:00:00Z" }), NOW);
    expect(b).toMatchObject({ show: true, cls: "act", title: "Radiation alert: solar particle event" });
  });

  test("test_watch", () => {
    const b = weatherBanner(sw({ status: "watch", reason: "X-class flare" }), NOW);
    expect(b).toMatchObject({ cls: "watch", title: "Space weather watch: X-class flare" });
  });

  test("test_unknown_and_stale", () => {
    const b = weatherBanner(sw({ status: "unknown", stale: true, cached_at: ago(31 * 60) }), NOW);
    expect(b).toMatchObject({ show: true, cls: "greyed", cachedText: "Cached data, 31 min old" });
    expect(weatherBanner(sw({ status: "unknown", cached_at: null }), NOW).cachedText).toBe("No space-weather data yet");
  });

  test("test_replay", () => {
    const b = weatherBanner(sw({ mode: "replay", status: "act", event_time: "2025-11-11T05:20:00Z" }), NOW);
    expect(b.replay).toBe(true);
    expect(b.title.startsWith("Replay (recorded event of 2025-11-11): ")).toBe(true);
  });

  test("test_disclaimer", () => {
    const d = "DONKI is research-grade; NOAA SWPC is the official forecast source.";
    expect(weatherBanner(sw({ disclaimer: d }), NOW).detail.endsWith(d)).toBe(true);
    expect(weatherBanner(sw({ disclaimer: "" }), NOW).detail.endsWith("DONKI is research information; the official forecast source is NOAA SWPC.")).toBe(true);
  });

  test("test_ack_text", () => {
    expect(weatherBanner(sw({ status: "act", ack: { crew: "crew-b", at: "2026-11-14T12:05:00Z", event_id: "E1" } }), NOW).ackText).toBe("Acknowledged by Crew B at 12:05 UTC");
    expect(weatherBanner(sw({ status: "act", ack: null }), NOW).ackText).toBe("Not yet acknowledged");
    expect(weatherBanner(sw({ status: "ok" }), NOW).ackText).toBeNull();
  });

  test("test_ack_button", () => {
    expect(ackState(sw({ status: "act", ack: null }), null)).toEqual({ enabled: false, hint: "Choose who is acknowledging." });
    expect(ackState(sw({ status: "act", ack: null }), "crew-a").enabled).toBe(true);
    expect(ackState(sw({ status: "act", ack: { crew: "crew-a", at: "x", event_id: "E1" } }), "crew-a").enabled).toBe(false);
  });
});
