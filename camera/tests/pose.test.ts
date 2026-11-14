import { describe, expect, test } from "vitest";
import { canUseCamera, createRecorder, recordingProblem } from "../src/pose";

describe("pose", () => {
  test("test_insecure_context", () => {
    const r = canUseCamera({ isSecureContext: false, navigator: {} as Navigator });
    expect(r).toEqual({
      ok: false,
      reason: "The camera needs https or localhost. Open this page on the hub machine at http://localhost:8000/camera/, or load a video file.",
    });
  });

  test("test_no_getusermedia", () => {
    const r = canUseCamera({ isSecureContext: true, navigator: {} as Navigator });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toContain("video file");
    expect(canUseCamera({ isSecureContext: true, navigator: { mediaDevices: { getUserMedia: () => {} } } as unknown as Navigator }).ok).toBe(true);
  });

  test("test_no_record_without_rvfc", () => {
    expect(recordingProblem({})).toEqual(expect.any(String));
    expect(recordingProblem({ requestVideoFrameCallback: () => 0 })).toBeNull();
  });

  test("recorder keeps both wrists and anchors the first frame", () => {
    const rec = createRecorder();
    expect(rec.firstFramePerfMs).toBeNull();
    rec.push({ tS: 0.1, landmarks: undefined });
    const first = rec.firstFramePerfMs;
    rec.push({ tS: 0.2, landmarks: undefined });
    expect(rec.samples).toHaveLength(2);
    expect(rec.firstFramePerfMs).toBe(first);
  });
});
