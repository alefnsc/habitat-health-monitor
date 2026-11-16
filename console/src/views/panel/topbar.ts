import { COPY } from "../../copy";
import type { LinkState, Session, SignalsBody, SpaceWeather, StatusBody } from "../../contract";
import { el } from "../../dom";
import { formatAge } from "../../format";
import { formatLightTime } from "../../model/guidance";
import { weatherBanner } from "../../model/nasa";
import { notableCounts } from "../../model/signals";
import { liveSource, type PanelClock } from "./source";

export interface TopData {
  status: StatusBody | null;
  sessions: Session[] | null;
  weather: SpaceWeather | null;
  link: LinkState | null;
}

function chip(dot: string, label: string, value: string): HTMLElement {
  return el("span", { class: "pchip" }, el("i", { class: `dot ${dot}` }), `${label} `, el("b", { text: value }));
}

/**
 * The panel's top strip: live sources at a glance and a UTC clock. `signals` (D45) draws the signals chip on its own
 * cadence; it is never called for a source without signals (the replay), so that strip has no signals chip.
 */
export function topBar(src: PanelClock = liveSource): {
  node: HTMLElement; update: (d: TopData) => void; signals: (b: SignalsBody | null) => void; dispose: () => void;
} {
  const age = (iso: string | null) => (iso ? formatAge((src.now() - Date.parse(iso)) / 1000) : COPY["status.none"]);
  const missing = src.replay ? COPY["panel.notInReplayShort"] : COPY["panel.noData"];
  const chips = el("div", { style: "display:contents" });
  const clock = el("span", { class: "clock" });
  const sig = el("span", { style: "display:contents" });
  const node = el("div", { class: "p-top" }, chips, sig, clock);
  const tick = () => {
    clock.textContent = `${new Date(src.now()).toISOString().slice(11, 19)} ${COPY["lanes.utc"]}`;
  };
  tick();
  const t = setInterval(tick, 1000);
  const update = (d: TopData) => {
    const cabin = d.status?.nodes.find((n) => n.node === "cabin-1") ?? null;
    // Age of the newest cabin reading: a node's last_seen is its connection time, not its last reading.
    // A replay has no node list, and its cabin readings come from the simulator node.
    const cabinAt = (d.status?.results ?? []).filter((r) => (src.replay ? r.ind.startsWith("cabin_") : r.node === "cabin-1"))
      .reduce<string | null>((m, r) => (!m || r.measured_at > m ? r.measured_at : m), null);
    const last = d.sessions?.[0] ?? null;
    const sw = d.weather ? weatherBanner(d.weather, src.now()) : null;
    chips.replaceChildren(
      src.replay
        ? chip("", COPY["panel.chipCabin"], cabinAt ? `${COPY["src.replay"]} · ${age(cabinAt)}` : missing)
        : chip(cabin?.online ? "ok" : "act", COPY["panel.chipCabin"],
          cabin ? `${cabin.online ? COPY["panel.live"] : COPY["panel.offline"]} · ${age(cabinAt ?? cabin.last_seen)}` : missing),
      chip(last && src.now() - Date.parse(last.started_at) < 3600_000 ? "ok" : "", COPY["panel.chipCamera"],
        last ? age(last.started_at) : COPY["panel.noSet"]),
      chip(d.weather ? (sw?.cls === "greyed" ? "" : sw!.cls) : "", COPY["panel.chipWeather"],
        d.weather ? (d.weather.status === "ok" && !d.weather.stale ? `${COPY["panel.quiet"]} · DONKI` : sw!.title) : missing),
      chip(d.link?.state === "contact" ? "ok" : d.link?.state === "blackout" ? "act" : "",
        COPY["panel.chipLink"], d.link ? formatLightTime(d.link.light_time_s, 1) : missing),
    );
  };
  /** null when the request failed: the chip says no data, never "0 notable". Replay notables are counted apart. */
  const signals = (b: SignalsBody | null) => {
    const { real, replay } = notableCounts(b);
    const text = !b ? missing
      : (replay ? COPY["panel.signalsNotableReplay"].replace("{m}", String(replay)) : COPY["panel.signalsNotable"])
        .replace("{n}", String(real));
    sig.replaceChildren(el("a", { href: "#/signals", class: "pchip-link" },
      chip(real > 0 ? "watch" : "", COPY["panel.chipSignals"], text)));
  };
  return { node, update, signals, dispose: () => clearInterval(t) };
}
