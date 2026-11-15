import { COPY } from "../../copy";
import type { LinkState, Session, SpaceWeather, StatusBody } from "../../contract";
import { el } from "../../dom";
import { formatAge } from "../../format";
import { formatLightTime } from "../../model/guidance";
import { weatherBanner } from "../../model/nasa";

export interface TopData {
  status: StatusBody | null;
  sessions: Session[] | null;
  weather: SpaceWeather | null;
  link: LinkState | null;
}

const age = (iso: string | null) => (iso ? formatAge((Date.now() - Date.parse(iso)) / 1000) : COPY["status.none"]);

function chip(dot: string, label: string, value: string): HTMLElement {
  return el("span", { class: "pchip" }, el("i", { class: `dot ${dot}` }), `${label} `, el("b", { text: value }));
}

/** The panel's top strip: live sources at a glance and a UTC clock. */
export function topBar(): { node: HTMLElement; update: (d: TopData) => void; dispose: () => void } {
  const chips = el("div", { style: "display:contents" });
  const clock = el("span", { class: "clock" });
  const node = el("div", { class: "p-top" }, chips, clock);
  const tick = () => {
    clock.textContent = `${new Date().toISOString().slice(11, 19)} ${COPY["lanes.utc"]}`;
  };
  tick();
  const t = setInterval(tick, 1000);
  const update = (d: TopData) => {
    const cabin = d.status?.nodes.find((n) => n.node === "cabin-1") ?? null;
    // Age of the newest cabin reading: a node's last_seen is its connection time, not its last reading.
    const cabinAt = (d.status?.results ?? []).filter((r) => r.node === "cabin-1")
      .reduce<string | null>((m, r) => (!m || r.measured_at > m ? r.measured_at : m), null);
    const last = d.sessions?.[0] ?? null;
    const sw = d.weather ? weatherBanner(d.weather, Date.now()) : null;
    chips.replaceChildren(
      chip(cabin?.online ? "ok" : "act", COPY["panel.chipCabin"],
        cabin ? `${cabin.online ? COPY["panel.live"] : COPY["panel.offline"]} · ${age(cabinAt ?? cabin.last_seen)}` : COPY["panel.noData"]),
      chip(last && Date.now() - Date.parse(last.started_at) < 3600_000 ? "ok" : "", COPY["panel.chipCamera"],
        last ? age(last.started_at) : COPY["panel.noSet"]),
      chip(d.weather ? (sw?.cls === "greyed" ? "" : sw!.cls) : "", COPY["panel.chipWeather"],
        d.weather ? (d.weather.status === "ok" && !d.weather.stale ? `${COPY["panel.quiet"]} · DONKI` : sw!.title) : COPY["panel.noData"]),
      chip(d.link?.state === "contact" ? "ok" : d.link?.state === "blackout" ? "act" : "",
        COPY["panel.chipLink"], d.link ? formatLightTime(d.link.light_time_s, 1) : COPY["panel.noData"]),
    );
  };
  return { node, update, dispose: () => clearInterval(t) };
}
