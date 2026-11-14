import { describe, expect, test } from "vitest";
import { ApiError } from "../src/api";
import { ENTRY_ROWS, defaultSrc, resendFailed, submitAll } from "../src/views/entry";
import { createSequencer } from "../src/payload";
import type { PostResult, ReadingMessage, StatusEntry } from "../src/contract";

const BOOT = 1794657600;
const entryOf = (ind: "body_temp" | "mood"): StatusEntry => ({
  ind, val: 1, unit: "C", status: "ok", rule_id: null, source_kind: null, source_ref: null, guidance_id: null,
  escalate_to: "self", measured_at: "2026-11-14T12:00:00.000Z", crew: "crew-a", src: "certified", dev: "manual",
  q: ["ok"], node: "manual", reading_id: 1,
});
const ok = (results: StatusEntry[] = [], duplicate = false): PostResult => ({
  id: 1, measured_at: "2026-11-14T12:00:00.000Z", duplicate, results,
});

describe("entry", () => {
  test("test_rows", () => {
    expect([...ENTRY_ROWS]).toEqual(["bp", "hr", "spo2", "body_temp", "glucose", "sleep_h", "mood", "symptom", "body_mass"]);
  });

  test("test_default_src", () => {
    for (const r of ["bp", "spo2", "body_temp", "glucose", "hr"] as const) expect(defaultSrc(r)).toBe("certified");
    for (const r of ["sleep_h", "mood", "symptom", "body_mass"] as const) expect(defaultSrc(r)).toBe("self");
  });

  test("test_body_mass_row", async () => {
    const posted: ReadingMessage[] = [];
    const post = async (m: ReadingMessage) => (posted.push(m), ok());
    await submitAll([{ ind: "body_mass", val: 70 }], "crew-a", createSequencer(BOOT), post);
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ ind: "body_mass", unit: "kg", dev: "manual", src: "self" });
    posted.length = 0;
    const r = await submitAll([{ ind: "body_mass", val: 19 }], "crew-a", createSequencer(BOOT), post);
    expect(posted).toHaveLength(0);
    expect(r.failed).toEqual([{ ind: "body_mass", error: "Body mass must be 20 to 300 kg.", message: null }]);
  });

  test("test_requires_crew", async () => {
    const post = async () => ok();
    const r = await submitAll([{ ind: "hr", val: 60 }], null, createSequencer(BOOT), post);
    expect(r.sent).toBe(0);
    expect(r.failed).toEqual([{ ind: "*", error: "Choose who this reading is for.", message: null }]);
  });

  test("test_submit_partial_failure", async () => {
    const post = async (m: ReadingMessage) => {
      if (m.ind === "mood") throw new ApiError(500, "HTTP 500");
      return ok([entryOf("body_temp")]);
    };
    const r = await submitAll(
      [{ ind: "body_temp", val: 36.8 }, { ind: "mood", val: 4 }], "crew-a", createSequencer(BOOT), post,
    );
    expect(r.sent).toBe(1);
    expect(r.results).toHaveLength(1);
    expect(r.failed).toHaveLength(1);
    expect(r.failed[0]).toMatchObject({ ind: "mood", error: "HTTP 500" });
    expect(r.failed[0].message).toMatchObject({ ind: "mood", seq: 2, boot: BOOT });
  });

  test("test_resend_same_seq", async () => {
    const failedPost = async (m: ReadingMessage) => {
      if (m.ind === "mood") throw new ApiError(500, "HTTP 500");
      return ok();
    };
    const first = await submitAll(
      [{ ind: "body_temp", val: 36.8 }, { ind: "mood", val: 4 }], "crew-a", createSequencer(BOOT), failedPost,
    );
    const posted: ReadingMessage[] = [];
    const r = await resendFailed(first.failed, async (m) => (posted.push(m), ok()));
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ ind: "mood", boot: BOOT, seq: 2 });
    expect(r.sent).toBe(1);
    expect(r.failed).toEqual([]);
  });

  test("test_duplicate_counts_as_sent", async () => {
    const r = await submitAll([{ ind: "hr", val: 60 }], "crew-a", createSequencer(BOOT), async () => ok([], true));
    expect(r.sent).toBe(1);
    expect(r.failed).toEqual([]);
  });
});
