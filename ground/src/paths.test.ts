import { describe, expect, it } from "vitest";
import { apiBase, replayUrl } from "./paths";

describe("replayUrl", () => {
  it("replayUrl_repo_base", () => {
    expect(replayUrl("/habitat-health-monitor/")).toBe("/habitat-health-monitor/replay.json");
  });
  it("replayUrl_root_base", () => {
    expect(replayUrl("/")).toBe("/replay.json");
  });
  it("replayUrl_missing_trailing_slash", () => {
    expect(replayUrl("/habitat-health-monitor")).toBe("/habitat-health-monitor/replay.json");
  });
});

describe("apiBase", () => {
  it("apiBase_live_default", () => {
    expect(apiBase("live", undefined)).toBe("");
  });
  it("apiBase_live_env", () => {
    expect(apiBase("live", "http://192.168.4.20:8100")).toBe("http://192.168.4.20:8100");
  });
  it("apiBase_replay", () => {
    expect(apiBase("replay", "http://192.168.4.20:8100")).toBe("");
  });
});
