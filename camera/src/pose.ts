import { timingProblem } from "../../vendor/ground-truth/demo/src/model/captureFlow";
import { wristSample, type WristSample } from "../../vendor/ground-truth/demo/src/pose/landmarks";
import type { FrameSample } from "../../vendor/ground-truth/demo/src/pose/source";
import { COPY } from "./copy";

export function canUseCamera(win: { isSecureContext: boolean; navigator: Navigator }): { ok: true } | { ok: false; reason: string } {
  if (!win.isSecureContext) return { ok: false, reason: COPY["insecure"] };
  if (!win.navigator.mediaDevices?.getUserMedia) return { ok: false, reason: COPY["noMediaDevices"] };
  return { ok: true };
}

// A refusal sentence when recording would use timestamps that are not video time, else null.
export function recordingProblem(video: { requestVideoFrameCallback?: unknown }): string | null {
  return timingProblem(typeof video.requestVideoFrameCallback === "function");
}

// Stores both wrists of every recorded frame. The side is chosen after the set (pickRecordedSide).
export function createRecorder() {
  const samples: WristSample[] = [];
  let firstFramePerfMs: number | null = null;
  return {
    samples,
    get firstFramePerfMs(): number | null {
      return firstFramePerfMs;
    },
    push(s: FrameSample): void {
      // Read inside the frame callback, so the anchor is the first recorded frame, not an HTTP response.
      if (firstFramePerfMs === null) firstFramePerfMs = performance.now();
      samples.push(wristSample(s.tS, s.landmarks));
    },
  };
}
