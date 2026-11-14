import { loadLandmarker, openCamera, openFile, detectOnce, track, type Tracker, type VideoSource } from "../../vendor/ground-truth/demo/src/pose/source";
import { LANDMARK, type Landmark } from "../../vendor/ground-truth/demo/src/pose/landmarks";
import { calibrateKnownLength, calibrateStature, type CalResult } from "./calibrate";
import { COPY } from "./copy";
import { canUseCamera, recordingProblem } from "./pose";

type Node = HTMLElement;
function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...kids: (Node | string)[]): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "text" ? (n.textContent = v) : n.setAttribute(k, v);
  n.append(...kids);
  return n;
}

export interface PageState {
  video: HTMLVideoElement;
  getSource(): VideoSource | null;
  getScale(): number | null;
  getLandmarker(): Awaited<ReturnType<typeof loadLandmarker>> | null;
}

export function mountCamera(root: HTMLElement): PageState {
  const video = h("video", { id: "preview", playsinline: "", muted: "" });
  const dot = h("div", { class: "wrist-dot", hidden: "" });
  const status = h("p", { role: "status" });
  const scaleOut = h("p", { id: "scale-out" });
  let source: VideoSource | null = null;
  let landmarker: Awaited<ReturnType<typeof loadLandmarker>> | null = null;
  let preview: Tracker | null = null;
  let scale: number | null = null;
  let frozen: Landmark[] | undefined;
  const taps: { x: number; y: number }[] = [];

  const stage = h("div", { class: "stage" }, video, dot);
  const camBtn = h("button", { type: "button", text: COPY["source.camera"] });
  const fileIn = h("input", { type: "file", accept: "video/*", id: "file" });
  const fileLabel = h("label", { for: "file", text: `${COPY["source.file"]} ` });
  const ready = async () => (landmarker ??= await loadLandmarker());
  const startPreview = async () => {
    const lm = await ready();
    preview?.stop();
    if (recordingProblem(video)) status.textContent = recordingProblem(video) ?? "";
    preview = track(video, lm, (s) => {
      const w = s.landmarks?.[LANDMARK.RIGHT_WRIST];
      dot.hidden = !w;
      if (w) {
        dot.style.left = `${w.x * 100}%`;
        dot.style.top = `${w.y * 100}%`;
      }
    }, (e) => (status.textContent = String(e)));
  };
  camBtn.addEventListener("click", async () => {
    const ok = canUseCamera({ isSecureContext: window.isSecureContext, navigator });
    if (!ok.ok) { status.textContent = ok.reason; return; }
    try { source?.release(); source = await openCamera(video, () => (status.textContent = "The camera stopped.")); await startPreview(); } catch (e) { status.textContent = String(e instanceof Error ? e.message : e); }
  });
  fileIn.addEventListener("change", async () => {
    const f = fileIn.files?.[0];
    if (!f) return;
    try { source?.release(); source = await openFile(video, f); await startPreview(); } catch (e) { status.textContent = String(e instanceof Error ? e.message : e); }
  });

  // Calibration
  const lenIn = h("input", { id: "known-length", type: "number", step: "0.01", value: "0.30" });
  const heightIn = h("input", { id: "stature", type: "number", step: "0.01", value: "1.75" });
  const freeze = h("button", { type: "button", text: COPY["calib.freeze"] });
  const showScale = (r: CalResult) => {
    if (r.ok) { scale = r.metersPerUnit; scaleOut.textContent = `${COPY["calib.result"]}: ${r.metersPerUnit.toFixed(3)} ${COPY["calib.unit"]}${r.note ? ` (${r.note})` : ""}`; }
    else { scaleOut.textContent = r.error; }
  };
  freeze.addEventListener("click", () => {
    preview?.stop();
    if (landmarker) frozen = detectOnce(video, landmarker);
    video.pause();
    taps.length = 0;
    scaleOut.textContent = COPY["calib.tapA"];
  });
  stage.addEventListener("click", (ev) => {
    if (!video.paused) return;
    const r = stage.getBoundingClientRect();
    taps.push({ x: (ev.clientX - r.left) / r.width, y: (ev.clientY - r.top) / r.height });
    scaleOut.textContent = taps.length === 1 ? COPY["calib.tapB"] : "";
  });
  const useKnown = h("button", { type: "button", text: COPY["calib.useKnown"] });
  useKnown.addEventListener("click", () => {
    if (taps.length < 2) { scaleOut.textContent = COPY["calib.tapA"]; return; }
    showScale(calibrateKnownLength(taps[0], taps[1], Number(lenIn.value)));
  });
  const useStature = h("button", { type: "button", text: COPY["calib.useStature"] });
  useStature.addEventListener("click", () => showScale(calibrateStature(Number(heightIn.value), frozen)));

  root.replaceChildren(
    h("div", { class: "banner", text: COPY["page.banner"] }),
    h("h1", { text: COPY["page.title"] }),
    h("p", { text: COPY["camera.estimate"] }),
    h("div", {}, camBtn, " ", fileLabel, fileIn),
    stage, status,
    h("h2", { text: COPY["calib.title"] }),
    h("div", {}, freeze, " ", h("label", { for: "known-length", text: `${COPY["calib.knownLength"]} ` }), lenIn, " ", useKnown),
    h("div", {}, h("label", { for: "stature", text: `${COPY["calib.stature"]} ` }), heightIn, " ", useStature),
    scaleOut,
  );
  return { video, getSource: () => source, getScale: () => scale, getLandmarker: () => landmarker };
}

const appRoot = typeof document !== "undefined" ? document.getElementById("app") : null;
if (appRoot) mountCamera(appRoot);
