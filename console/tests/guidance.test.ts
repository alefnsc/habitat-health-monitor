import { describe, expect, test } from "vitest";
import { escalationSteps, formatLightTime, guidanceFor, whyFor, type GuidanceItem } from "../src/model/guidance";
import type { LinkState } from "../src/contract";

const item = (o: Partial<GuidanceItem>): GuidanceItem => ({ id: "x", rule_id: "x", status: "watch", do_now: "d", tell: "t", escalate_to: "cmo", risk_title: "", risk_url: "", ...o });
const ITEMS: GuidanceItem[] = [
  item({ id: "hr_rest_high.watch", do_now: "Sit and rest 5 minutes, then measure again.", tell: "Tell the CMO if it stays above 90 bpm at rest.", risk_title: "Cardiovascular", risk_url: "https://humanresearchroadmap.nasa.gov/Risks/?i=179" }),
  item({ id: "quiet.watch", tell: "—" }),
  item({ id: "default.unknown", do_now: "Not assessed. Check contact and measure again." }),
  item({ id: "default.hr", status: "info", why: "Resting heart rate shows how hard the heart works. (fixture)" }),
  item({ id: "default.mood", status: "info" }),
];
const link = (o: Partial<LinkState> = {}): LinkState => ({ state: "contact", light_time_s: 720, time_scale: 1, queue_len: 0, last_blackout: null, ...o });

describe("guidance", () => {
  test("test_lookup", () => {
    expect(guidanceFor({ guidance_id: "hr_rest_high.watch", status: "watch" }, ITEMS)).toMatchObject({
      doNow: "Sit and rest 5 minutes, then measure again.", tell: "Tell the CMO if it stays above 90 bpm at rest.",
      riskTitle: "Cardiovascular", riskUrl: "https://humanresearchroadmap.nasa.gov/Risks/?i=179",
    });
  });
  test("test_dash_tell", () => {
    expect(guidanceFor({ guidance_id: "quiet.watch", status: "watch" }, ITEMS).tell).toBeNull();
  });
  test("test_default_unknown", () => {
    expect(guidanceFor({ guidance_id: null, status: "unknown" }, ITEMS).doNow).toBe("Not assessed. Check contact and measure again.");
  });
  test("test_missing", () => {
    const g = guidanceFor({ guidance_id: "foo.watch", status: "watch" }, ITEMS);
    expect(g.doNow).toBeNull();
    expect(g.disclaimer).toBe("This is not a diagnosis.");
  });
  test("test_why_lookup", () => {
    expect(whyFor("hr", ITEMS)).toBe("Resting heart rate shows how hard the heart works. (fixture)");
    expect(whyFor("mood", ITEMS)).toBeNull();
    expect(whyFor("glucose", ITEMS)).toBeNull();
  });
  test("test_light_time", () => {
    expect(formatLightTime(720, 1)).toBe("12 min one-way");
    expect(formatLightTime(720, 60)).toBe("12 min one-way (demo: 12 s)");
    expect(formatLightTime(1342, 1)).toBe("22 min 22 s one-way");
    expect(formatLightTime(185, 1)).toBe("3 min 5 s one-way");
  });
  test("test_steps_cmo", () => {
    const s = escalationSteps({ status: "watch", escalate_to: "cmo" }, link());
    expect(s.map((x) => x.text)).toEqual(["Note it yourself", "Tell the crew medical officer", "Tell the flight surgeon: message arrives in 12 min one-way"]);
    expect(s.map((x) => x.current)).toEqual([false, true, false]);
  });
  test("test_act", () => {
    expect(escalationSteps({ status: "act", escalate_to: "flight_surgeon" }, link()).map((x) => x.current)).toEqual([false, false, true]);
  });
  test("test_blackout", () => {
    expect(escalationSteps({ status: "act", escalate_to: "flight_surgeon" }, link({ state: "blackout" }))[2].text.endsWith("Link in blackout: your message will queue.")).toBe(true);
  });
  test("test_unreachable", () => {
    expect(escalationSteps({ status: "act", escalate_to: "flight_surgeon" }, link({ state: "unreachable" }))[2].text).toBe(
      "Tell the flight surgeon: message arrives in 12 min one-way. Link simulator not reachable; light time from its config file.",
    );
  });
  test("test_link_null", () => {
    expect(escalationSteps({ status: "act", escalate_to: "flight_surgeon" }, null)[2].text).toBe("Tell the flight surgeon: light time unknown");
  });
  test("test_ok_status", () => {
    expect(escalationSteps({ status: "ok", escalate_to: "self" }, link()).some((x) => x.current)).toBe(false);
  });
});
