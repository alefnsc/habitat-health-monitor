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
  let opening = false;
  let run = 0; // bumped by stop(), so a camera that opens after stop() is closed at once

  const stop = () => {
    run++;
    opening = false;
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
    const mine = ++run;
    opening = true;
    let opened: MediaStream;
    try {
      opened = await deps.getStream();
    } catch (e) {
      if (mine === run) status.textContent = COPY["food.scanCameraError"] + (e instanceof Error ? e.message : String(e));
      opening = false;
      return;
    }
    if (mine !== run) {
      opened.getTracks().forEach((t) => t.stop());
      return;
    }
    opening = false;
    stream = opened;
    video.srcObject = stream;
    video.hidden = false;
    await video.play().catch(() => {});
    if (mine !== run) return; // stopped while the video was starting; stop() already closed the camera
    scan.textContent = COPY["food.scanStop"];
    status.textContent = COPY["food.scanLooking"];
    timer = setInterval(async () => {
      const cat = getCatalog();
      if (busy || !cat) return;
      busy = true;
      try {
        const texts = (await detector.detect(video)).map((b) => b.rawValue);
        if (mine !== run) return; // a frame read before Stop was pressed
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

  scan.addEventListener("click", () => (stream || opening ? stop() : void start()));
  use.addEventListener("click", () => {
    const cat = getCatalog();
    if (!cat) {
      status.textContent = COPY["food.scanCatalogLoading"];
      return;
    }
    const id = parsePackCode(code.value, cat);
    if (id) {
      code.value = "";
      pick(id);
    } else status.textContent = COPY["food.scanUnknown"];
  });

  const node = el("div", { class: "food-scan" },
    scan, " ", el("label", { for: "food-code", text: `${COPY["food.packCode"]} ` }), code, " ", use, status, video);
  return { node, stop };
}
