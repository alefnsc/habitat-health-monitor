/**
 * Camera or video file in, `{ tS, landmarks }` per video frame out. DOM and the pose library only:
 * the mapping to PoseFrame is in landmarks.ts, the arithmetic is nowhere in this file.
 *
 * Nothing here stores a frame or a video. The pose model and the WASM runtime are served from this page's own origin
 * (public/models and public/mediapipe/wasm), so the page contacts no third-party host. The library still tries to post
 * usage metrics to Google every 60 s (per its own privacy notice, "metrics about the performance and utilization of the
 * APIs"); index.html blocks that with a Content-Security-Policy that sets connect-src to 'self', and
 * test/network.test.ts pins the policy.
 */

import { FilesetResolver, PoseLandmarker } from "@mediapipe/tasks-vision";
import type { Landmark } from "./landmarks";

/**
 * Same-origin paths. The model is committed (public/models, with NOTICE.md and its SHA-256, checked by
 * scripts/verify-model.mjs); the WASM files are copied from the pinned @mediapipe/tasks-vision package into
 * public/mediapipe/wasm by scripts/copy-wasm.mjs before `dev` and `build`, and are not committed.
 */
export const POSE_MODEL_URL = `${import.meta.env.BASE_URL}models/pose_landmarker_lite.task`;
export const POSE_WASM_BASE = `${import.meta.env.BASE_URL}mediapipe/wasm`;

// ---------------------------------------------------------------------------
// The pose model
// ---------------------------------------------------------------------------

let landmarkerPromise: Promise<PoseLandmarker> | null = null;

/** Loads the model once; a failed load can be retried. */
export function loadLandmarker(): Promise<PoseLandmarker> {
  if (!landmarkerPromise) {
    landmarkerPromise = FilesetResolver.forVisionTasks(POSE_WASM_BASE)
      .then((fileset) =>
        PoseLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: POSE_MODEL_URL },
          runningMode: "VIDEO",
          numPoses: 1,
        }),
      )
      .catch((error: unknown) => {
        landmarkerPromise = null;
        throw error;
      });
  }
  return landmarkerPromise;
}

// ---------------------------------------------------------------------------
// Video sources
// ---------------------------------------------------------------------------

export interface VideoSource {
  kind: "camera" | "file";
  /** Stops the camera tracks and clears the video element, or revokes the file's object URL. */
  release(): void;
}

function prepare(video: HTMLVideoElement): void {
  video.muted = true;
  video.playsInline = true;
  video.setAttribute("playsinline", "");
}

/**
 * The rear camera if there is one. Needs a secure page (HTTPS or localhost). `onEnded` is called if the camera stops
 * by itself (unplugged, permission revoked, taken by another app). If anything fails after the camera was granted,
 * its tracks are stopped before the error is thrown.
 */
export async function openCamera(video: HTMLVideoElement, onEnded: () => void): Promise<VideoSource> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This page cannot reach a camera. Phones only allow it on HTTPS (use npm run dev:https) or on localhost.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
  const stop = (): void => {
    for (const track of stream.getTracks()) track.stop();
    if (video.srcObject === stream) {
      video.pause();
      video.srcObject = null;
    }
  };
  try {
    prepare(video);
    video.removeAttribute("src");
    video.srcObject = stream;
    for (const track of stream.getVideoTracks()) track.addEventListener("ended", onEnded);
    await video.play();
  } catch (error) {
    stop();
    throw error;
  }
  return { kind: "camera", release: stop };
}

/** A video file chosen by the user. It is played from an object URL: it is never uploaded or stored. */
export async function openFile(video: HTMLVideoElement, file: File): Promise<VideoSource> {
  const url = URL.createObjectURL(file);
  prepare(video);
  video.srcObject = null;
  video.src = url;
  try {
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve();
      video.onerror = () => reject(new Error("This browser cannot play that video file."));
    });
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
  video.onloadedmetadata = null;
  video.onerror = null;
  return {
    kind: "file",
    release() {
      if (video.src === url) {
        video.pause();
        video.removeAttribute("src");
        video.load();
      }
      URL.revokeObjectURL(url);
    },
  };
}

/** Waits for a seek to the start of the video to finish, so that no frame from the old position is processed as the first. */
export function seekToStart(video: HTMLVideoElement): Promise<void> {
  if (video.currentTime === 0 && !video.seeking) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, 3000);
    video.addEventListener(
      "seeked",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
    video.currentTime = 0;
  });
}

// ---------------------------------------------------------------------------
// Frames
// ---------------------------------------------------------------------------

export interface FrameSample {
  /** Seconds. The frame's own media time (see `Tracker.timing`). */
  tS: number;
  /** The first pose's landmarks, or undefined when nothing was detected. */
  landmarks: Landmark[] | undefined;
}

export interface Tracker {
  /**
   * "frame": the time of each sample is the video frame's own `mediaTime` (requestVideoFrameCallback), which
   * is what the capture package needs. "callback": this browser has no requestVideoFrameCallback, so the time is
   * `video.currentTime` read when an animation frame ran, which carries scheduling jitter that the pipeline cannot
   * tell from motion. The view says so.
   */
  timing: "frame" | "callback";
  stop(): void;
}

/** The pose model's clock must increase over the lifetime of the landmarker; every run starts after the last one ended. */
let clockOffsetMs = 0;
const RUN_GAP_MS = 1000;

/**
 * One detection on the frame the video shows now, for freezing a frame. Stop any tracker first: the pose model's clock
 * only moves forward, and this moves it past every earlier run, so a tracker started afterwards begins later still.
 */
export function detectOnce(video: HTMLVideoElement, landmarker: PoseLandmarker): Landmark[] | undefined {
  clockOffsetMs += RUN_GAP_MS;
  return landmarker.detectForVideo(video, clockOffsetMs).landmarks[0];
}

/**
 * Delivers one sample per new video frame. A `mediaTime` is never processed twice and never out of order (a seek
 * backwards, a loop or a repeated callback is skipped), so every sample's `tS` is strictly increasing.
 */
export function track(video: HTMLVideoElement, landmarker: PoseLandmarker, onSample: (sample: FrameSample) => void, onError: (error: unknown) => void): Tracker {
  const hasFrameCallback = typeof video.requestVideoFrameCallback === "function";
  const runOffsetMs = clockOffsetMs + RUN_GAP_MS;
  let lastMediaS = Number.NEGATIVE_INFINITY;
  let stopped = false;
  let handle = 0;

  function process(mediaS: number): void {
    if (!(mediaS > lastMediaS)) return;
    lastMediaS = mediaS;
    const detectMs = runOffsetMs + mediaS * 1000;
    clockOffsetMs = Math.max(clockOffsetMs, detectMs);
    const result = landmarker.detectForVideo(video, detectMs);
    onSample({ tS: mediaS, landmarks: result.landmarks[0] });
  }

  function schedule(): void {
    if (stopped) return;
    if (hasFrameCallback) {
      handle = video.requestVideoFrameCallback((_now, metadata) => step(metadata.mediaTime));
    } else {
      handle = requestAnimationFrame(() => step(video.currentTime));
    }
  }

  function step(mediaS: number): void {
    if (stopped) return;
    try {
      process(mediaS);
    } catch (error) {
      stopped = true;
      onError(error);
      return;
    }
    schedule();
  }

  schedule();
  return {
    timing: hasFrameCallback ? "frame" : "callback",
    stop() {
      stopped = true;
      if (hasFrameCallback) video.cancelVideoFrameCallback(handle);
      else cancelAnimationFrame(handle);
    },
  };
}
