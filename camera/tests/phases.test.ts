import { describe, expect, test } from "vitest";
import type { RepResult, SessionResult } from "@ground-truth/capture";
import type { CaptureOutcome } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { COPY } from "../src/copy";
import { createSequencer } from "../src/seq";
import { ENVIRONMENT_MENU, gNoteText, resultView, toRepMessages } from "../src/reps";

const rep = (o: Partial<RepResult>): RepResult => ({
  startS: 0, durationS: 2, liftDurationS: 1, filterLimited: false, rangeOfMotionM: 0.5, pathLengthM: 1,
  trimmedRangeFraction: 1, positiveWorkJ: 10, negativeWorkJ: -5, peakForceN: 100, impulseNs: 1, ...o,
});
const ok = (reps: RepResult[]): SessionResult =>
  ({ ok: true, reps, totalPositiveWorkJ: 0, maxPeakForceN: 0, quality: {}, provenance: { confidence: "MEDIUM" } }) as unknown as SessionResult;
const ctx = () => ({
  session: "s-1794657600000", g: 9.81, mass_kg: 10, boot: 1794657600, seq: createSequencer(1794657600),
  firstFramePerfMs: 1000, nowPerfMs: 9000,
});

describe("phase split (D39)", () => {
  test("test_phase_fields_from_vendored_result", () => {
    const [m] = toRepMessages(
      ok([rep({ startS: 1.2, durationS: 2.1, liftDurationS: 0.9, positiveWorkJ: 38.6, negativeWorkJ: -12.5 })]),
      ctx(),
    );
    expect(m).toMatchObject({ work_j: 38.6, work_ecc_j: 12.5, t0_ms: 1200, t1_ms: 3300, t_turn_ms: 2100, t_con_ms: 900, t_ecc_ms: 1200 });
    expect(m.t_con_ms + m.t_ecc_ms).toBe(m.t1_ms - m.t0_ms);
  });

  test("test_turnaround_clamped_inside_rep", () => {
    const [m] = toRepMessages(ok([rep({ startS: 1, durationS: 2, liftDurationS: 5 })]), ctx());
    expect(m.t_turn_ms).toBe(3000);
    expect(m.t_ecc_ms).toBe(0);
  });

  test("test_no_negative_zero_work", () => {
    const [m] = toRepMessages(ok([rep({ negativeWorkJ: 0 })]), ctx());
    expect(Object.is(m.work_ecc_j, -0)).toBe(false);
    expect(m.work_ecc_j).toBe(0);
  });

  test("test_result_rows_show_both_phases", () => {
    const outcome = {
      kind: "measured",
      reps: [{ index: 1, rep: rep({ negativeWorkJ: -7, liftDurationS: 0.8, durationS: 2 }), notes: [] }],
      confidence: "MEDIUM",
    } as unknown as CaptureOutcome;
    const [row] = resultView(outcome).rows;
    expect(row.eccJ).toBe(7);
    expect(row.tConS).toBeCloseTo(0.8, 9);
    expect(row.tEccS).toBeCloseTo(1.2, 9);
    expect(COPY["result.work"]).toBe("Concentric work (J)");
    expect(COPY["result.workEcc"]).toBe("Eccentric work (J)");
    expect(COPY["result.tCon"]).toBe("Lift time (s)");
    expect(COPY["result.tEcc"]).toBe("Lowering time incl. top pause (s)");
  });

  test("test_configured_g_line_comes_from_the_menu", () => {
    for (const e of ENVIRONMENT_MENU) {
      expect(gNoteText(e.g)).toBe(`Work uses the configured g: ${e.g.toFixed(2)} m/s\u00b2 (${e.label})`);
    }
    expect(gNoteText(ENVIRONMENT_MENU[0].g)).toContain("Earth");
    expect(gNoteText(ENVIRONMENT_MENU[1].g)).toContain("Moon");
    expect(gNoteText(7)).toContain("(custom)");
  });
});
