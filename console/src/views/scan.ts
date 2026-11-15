/** Pack scanner on the food screen (D44). It only picks a catalogue food; the crew still logs the meal. */
import { COPY } from "../copy";
import { el } from "../dom";
import { firstKnownCode, parsePackCode } from "../model/scan";

type Ids = { items: readonly { id: string }[] };
interface Detector { detect(src: HTMLVideoElement): Promise<{ rawValue: string }[]> }
export interface ScanDeps {
  /** The browser's built-in QR detector, or null when the browser has none. */
  detector(): Detector | null;
  getStream(): Promise<MediaStream>;
}

const FRAME_MS = 250;

const browserDeps: ScanDeps = {
  detector() {
    const D = (globalThis as { BarcodeDetector?: new (o: { formats: string[] }) => Detector }).BarcodeDetector;
    return D && typeof navigator.mediaDevices?.getUserMedia === "function" ? new D({ formats: ["qr_code"] }) : null;
  },
  getStream: () => navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false }),
};

export function packScanner(getCatalog: () => Ids | null, onPick: (id: string) => void, deps: ScanDeps = browserDeps) {
  const status = el("p", { class: "footnote", role: "status" });
  const video = el("video", { playsinline: true, muted: true, class: "food-scan-video" });
  video.hidden = true;
  const scan = el("button", { type: "button", text: COPY["food.scanPack"] });
  const code = el("input", { id: "food-code", type: "text", autocomplete: "off", spellcheck: false });
  const use = el("button", { type: "button", text: COPY["food.useCode"] });
  let stream: MediaStream | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let busy = false;

  const stop = () => {
    if (timer !== null) clearInterval(timer);
    timer = null;
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    scan.textContent = COPY["food.scanPack"];
  };

  const pick = (id: string) => {
    stop();
    status.textContent = "";
    onPick(id);
  };

  const start = async () => {
    const detector = deps.detector();
    if (!detector) {
      status.textContent = COPY["food.scanUnavailable"];
      return;
    }
    try {
      stream = await deps.getStream();
    } catch (e) {
      status.textContent = COPY["food.scanCameraError"] + (e instanceof Error ? e.message : String(e));
      return;
    }
    video.srcObject = stream;
    video.hidden = false;
    await video.play().catch(() => {});
    scan.textContent = COPY["food.scanStop"];
    status.textContent = COPY["food.scanLooking"];
    timer = setInterval(async () => {
      const cat = getCatalog();
      if (busy || !cat) return;
      busy = true;
      try {
        const texts = (await detector.detect(video)).map((b) => b.rawValue);
        const id = firstKnownCode(texts, cat);
        if (id) pick(id);
        else if (texts.length) status.textContent = COPY["food.scanUnknown"];
      } catch {
        /* a frame that cannot be read is skipped */
      } finally {
        busy = false;
      }
    }, FRAME_MS);
  };

  scan.addEventListener("click", () => (stream ? stop() : void start()));
  use.addEventListener("click", () => {
    const cat = getCatalog();
    const id = cat ? parsePackCode(code.value, cat) : null;
    if (id) {
      code.value = "";
      pick(id);
    } else status.textContent = COPY["food.scanUnknown"];
  });

  const node = el("div", { class: "food-scan" },
    scan, " ", el("label", { for: "food-code", text: `${COPY["food.packCode"]} ` }), code, " ", use, status, video);
  return { node, stop };
}
