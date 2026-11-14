import type { Spot } from "./habitat";
import type { LinkFrame } from "./linkview";

const TIMES = "×";
const ARROW = "→";
const DOT = "·";

function num(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function causeLabel(c: LinkFrame["cause"]): string {
  return c === "scheduled" || c === "unreachable" ? c : "cause unknown";
}

// ---- Habitat map ---------------------------------------------------------------------------

interface Box {
  spot: Spot;
  x: number;
  y: number;
  w: number;
  lines: string[];
}

const BOX_H = 64;
const BOXES: Box[] = [
  { spot: "cabin", x: 36, y: 72, w: 168, lines: ["UNO I/O board", "DHT11 · buzzer"] },
  { spot: "camera", x: 244, y: 72, w: 100, lines: ["Camera", "reps"] },
  { spot: "tilt", x: 352, y: 72, w: 100, lines: ["Tilt node", "NodeMCU", "KY-017"] },
  { spot: "ring", x: 36, y: 200, w: 168, lines: ["Ring import", "hr · SpO₂ · sleep"] },
  { spot: "hub", x: 260, y: 200, w: 150, lines: ["Raspberry Pi", "hub · console"] },
];

const ROOMS = [
  { x: 20, y: 40, w: 200, h: 118, label: "Cabin" },
  { x: 232, y: 40, w: 228, h: 118, label: "Exercise area" },
  { x: 20, y: 170, w: 200, h: 110, label: "Crew (wearable)" },
  { x: 232, y: 170, w: 228, h: 110, label: "Hub" },
];

// [x1, y1, x2, y2, label, label x, label y, dashed]
const WIRES: [number, number, number, number, string, number, number, boolean][] = [
  [120, 136, 280, 200, "USB serial", 190, 166, false],
  [294, 136, 320, 200, "HTTP", 300, 166, false],
  [402, 136, 390, 200, "Wi-Fi · MQTT", 412, 166, false],
  [204, 232, 260, 232, "import", 232, 226, true],
];

function boxSvg(b: Box, lit: Set<Spot>, present: Set<Spot> | null): string {
  const absent = present !== null && !present.has(b.spot);
  const cls = `node${lit.has(b.spot) ? " lit" : ""}${absent ? " absent" : ""}`;
  const cx = b.x + b.w / 2;
  const [title, ...rest] = b.lines;
  const sub = rest.map((l, i) => `<text class="node-sub" x="${cx}" y="${b.y + 40 + i * 13}">${l}</text>`).join("");
  const note = absent
    ? `<text class="node-note" x="${cx}" y="${b.y + BOX_H + 12}">no data in this replay</text>`
    : "";
  return `<g class="${cls}" data-spot="${b.spot}">
      <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${BOX_H}" rx="8"/>
      <text class="node-title" x="${cx}" y="${b.y + 22}">${title}</text>${sub}${note}
    </g>`;
}

function habitatSvg(lit: Set<Spot>, present: Set<Spot> | null, holdS: number | null): string {
  const rooms = ROOMS.map(
    (r) => `<rect class="room" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="10"/>
      <text class="room-label" x="${r.x + 10}" y="${r.y + 16}">${r.label}</text>`,
  ).join("");
  const wires = WIRES.map(
    ([x1, y1, x2, y2, label, lx, ly, dashed]) =>
      `<line class="wire${dashed ? " dashed" : ""}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>
      <text class="wire-label" x="${lx}" y="${ly}">${label}</text>`,
  ).join("");
  const legend = holdS === null
    ? "A box lights when its data reaches Earth."
    : `A box lights when its data reaches Earth, ${num(holdS)} s after it was sent (demo scale).`;
  return `<svg class="habitat" viewBox="0 0 480 322" role="img"
      aria-label="Habitat sensor map: cabin UNO I/O board with DHT11 and buzzer; exercise area camera and tilt node (NodeMCU with KY-017); Raspberry Pi hub; ring import">
    <text class="ov-title" x="12" y="18">Habitat on Mars ${DOT} where each sensor sits</text>
    <rect class="wall" x="8" y="28" width="464" height="264" rx="16"/>
    ${rooms}${wires}
    <path class="uplink" d="M410 232 H446 M452 224 a9 9 0 0 1 0 16 M458 218 a15 15 0 0 1 0 28"/>
    ${BOXES.map((b) => boxSvg(b, lit, present)).join("")}
    <text class="ov-legend" x="12" y="312">${legend}</text>
  </svg>`;
}

// ---- Mars link -----------------------------------------------------------------------------

const LX0 = 86;
const LX1 = 394;
const LY = 130;
const lx = (x: number) => LX0 + x * (LX1 - LX0);

function linkSvg(f: LinkFrame): string {
  const big = f.lightTimeMin === null
    ? `<text class="lt-none" x="240" y="54">Light-time not reported yet</text>`
    : `<text class="lt" x="240" y="54">${num(f.lightTimeMin)} min one-way</text>`;
  const scale = f.timeScale !== null && f.holdS !== null
    ? f.timeScale > 1
      ? `light-time ${DOT} demo ${TIMES}${num(f.timeScale)} ${ARROW} ${num(f.holdS)} s on this page`
      : `light-time ${DOT} real scale`
    : "";
  const gap = f.gap
    ? `<line class="gap" x1="${lx(f.gap[0])}" y1="${LY}" x2="${lx(f.gap[1])}" y2="${LY}"/>`
    : "";
  const packets = f.packets
    .map((p) => `<circle class="packet${p.big ? " big" : ""}" cx="${lx(p.x)}" cy="${LY}" r="${p.big ? 8 : 4.5}"/>`)
    .join("");
  let badge = "";
  if (f.gap) {
    // Above the line, over the middle of the gap, so packets and the gap stay visible.
    const w = 168;
    const mid = Math.min(Math.max(lx((f.gap[0] + f.gap[1]) / 2), LX0 + w / 2), LX1 - w / 2);
    badge = `<g class="blackout">
        <rect x="${mid - w / 2}" y="${LY - 44}" width="${w}" height="26" rx="13"/>
        <text x="${mid}" y="${LY - 26}">BLACKOUT ${DOT} ${causeLabel(f.cause)}</text>
      </g>`;
  }
  const n = f.packets.length;
  const flight = f.lightTimeMin === null ? "" : `${n} packet${n === 1 ? "" : "s"} in flight`;
  const label = `Mars to Earth link${f.lightTimeMin === null ? "" : `, ${num(f.lightTimeMin)} min one-way light-time`}, ${flight || "no packets shown"}${f.gap ? ", blackout" : ""}`;
  return `<svg class="link${f.gap ? " in-blackout" : ""}" viewBox="0 0 480 206" role="img" aria-label="${label}">
    <text class="ov-title" x="12" y="18">Mars ${ARROW} Earth link (simulated)</text>
    ${big}
    <text class="lt-sub" x="240" y="74">${scale}</text>
    <line class="link-line" x1="${LX0}" y1="${LY}" x2="${LX1}" y2="${LY}"/>
    ${gap}${packets}${badge}
    <circle class="planet mars" cx="52" cy="${LY}" r="28"/>
    <circle class="planet earth" cx="428" cy="${LY}" r="28"/>
    <text class="end-name" x="52" y="178">Mars</text>
    <text class="end-name" x="428" y="178">Earth</text>
    <text class="end-state start${f.marsDown ? " down" : ""}" x="14" y="196">${f.marsDown ? "link down, queueing" : "sending"}</text>
    <text class="end-state end${f.earthDark ? " down" : ""}" x="466" y="196">${f.earthDark ? "no signal" : "receiving"}</text>
    <text class="lt-sub" x="240" y="162">${flight}</text>
  </svg>`;
}

/** Draw the habitat map and the Mars link side by side. `present` is null outside replay mode. */
export function renderOverview(
  root: HTMLElement,
  frame: LinkFrame,
  lit: Set<Spot>,
  present: Set<Spot> | null,
): void {
  root.innerHTML = `<section class="overview" aria-label="Habitat and link overview">
    ${habitatSvg(lit, present, frame.holdS)}${linkSvg(frame)}</section>`;
}
