import { COPY } from "../../copy";
import type { LinkState } from "../../contract";
import { el } from "../../dom";
import { formatLightTime } from "../../model/guidance";
import { holdMs, lightText, positions, prune, queueAlert, resume, type Packet } from "../../model/panel/link";
import { hubEvents } from "../../state";
import { card } from "./common";

const X0 = 64;
const X1 = 416;
const Y = 104;
// Static SVG skeleton (parsed by the browser, so no namespace string is needed); dynamic parts are filled by class.
const SKELETON = `<svg class="linkstrip" viewBox="0 0 480 190" role="img">
  <text class="lt" x="240" y="40" text-anchor="middle"></text>
  <text class="demo" x="240" y="62" text-anchor="middle"></text>
  <line class="line" x1="${X0}" y1="${Y}" x2="${X1}" y2="${Y}"></line>
  <g class="pk"></g>
  <circle class="planet mars" cx="${X0 - 18}" cy="${Y}" r="24"></circle>
  <circle class="planet earth" cx="${X1 + 18}" cy="${Y}" r="24"></circle>
  <text class="mars-name" x="${X0 - 18}" y="${Y + 46}" text-anchor="middle"></text>
  <text class="earth-name" x="${X1 + 18}" y="${Y + 46}" text-anchor="middle"></text>
  <text class="state" x="240" y="178" text-anchor="middle"></text>
</svg>`;

/** Card 5: the Mars-to-Earth link. Each alert from the hub crosses the line in the demo hold time. */
export function linkCard(): { node: HTMLElement; update: (l: LinkState | null) => void; dispose: () => void } {
  const c = card("p-link", "5", COPY["panel.link"]);
  c.sub.textContent = COPY["panel.linkSim"];
  let link: LinkState | null = null;
  let packets: Packet[] = [];
  const holder = el("div");
  holder.innerHTML = SKELETON;
  const svg = holder.firstElementChild as SVGSVGElement;
  const part = (cls: string) => svg.querySelector(`.${cls}`) as SVGElement;
  const lt = part("lt");
  const demo = part("demo");
  const pk = part("pk");
  const state = part("state");
  part("mars-name").textContent = COPY["panel.mars"];
  part("earth-name").textContent = COPY["panel.earth"];
  const caption = el("p", { class: "kv" });
  const counts = el("p", { class: "note" });
  c.body.append(svg, caption, counts);

  const draw = () => {
    if (!link) {
      lt.textContent = COPY["panel.noData"];
      return;
    }
    const hold = holdMs(link);
    packets = prune(packets, Date.now(), hold);
    const { moving: xs, waiting } = positions(packets, Date.now(), hold);
    pk.innerHTML = xs.map((x) => `<circle class="pkt" cx="${(X0 + x * (X1 - X0)).toFixed(1)}" cy="${Y}" r="7"></circle>`).join("");
    lt.textContent = formatLightTime(link.light_time_s, 1);
    demo.textContent = link.time_scale > 1
      ? COPY["panel.demo"].replace("{s}", String(link.time_scale)).replace("{h}", lightText(link.light_time_s / link.time_scale))
      : "";
    state.textContent = COPY[`panel.state.${link.state}`];
    svg.setAttribute("aria-label", `${COPY["panel.link"]}: ${lt.textContent}. ${state.textContent}`);
    caption.textContent = COPY["panel.linkCaption"].replace("{t}", lightText(link.light_time_s));
    counts.textContent = `${xs.length} ${COPY["panel.inFlight"]} · ${waiting} ${COPY["panel.waitingAtMars"]}`;
  };
  let raf = 0;
  let moving = false;
  const tick = () => {
    // Redraw per frame only while a packet is on the line (plus one frame to clear it).
    const busy = !!link && packets.some((p) => p.startMs !== null && Date.now() - p.startMs <= holdMs(link!));
    if (busy || moving) draw();
    moving = busy;
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  const setLink = (l: LinkState) => {
    link = l;
    packets = resume(packets, Date.now(), l.state); // back in contact: the queue leaves Mars now
  };
  const offAlert = hubEvents.onAlert(() => {
    packets = queueAlert(packets, Date.now(), link?.state ?? "unreachable");
    draw();
  });
  const offLink = hubEvents.onLink((l) => {
    setLink(l);
    draw();
  });
  return {
    node: c.node,
    update: (l) => {
      if (l) setLink(l);
      draw();
    },
    dispose: () => {
      cancelAnimationFrame(raf);
      offAlert();
      offLink();
    },
  };
}
