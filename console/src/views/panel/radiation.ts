import { COPY } from "../../copy";
import type { IssReference, SpaceWeather } from "../../contract";
import { el } from "../../dom";
import { doseBar, weatherBanner } from "../../model/nasa";
import { card } from "./common";
import { copyFor, liveSource, type CardSource } from "./source";

export interface RadiationData {
  ref: IssReference | null;
  weather: SpaceWeather | null;
}

/** Radiation: career effective-dose estimate against the NASA limit, and the DONKI space-weather state. */
export function radiationCard(src: CardSource = liveSource): { node: HTMLElement; update: (d: RadiationData) => void } {
  const c = card("p-rad", "", COPY["panel.radiation"]);
  c.sub.textContent = COPY["panel.radSources"];
  const update = (d: RadiationData) => {
    const parts: HTMLElement[] = [];
    const dose = d.ref ? doseBar(d.ref.dose) : null;
    if (dose?.showBar) {
      parts.push(
        el("div", { class: "kv", text: `${COPY["panel.dose"]}: ${dose.effectiveText}` }),
        el("div", { class: "dose-track" }, el("div", { class: "fill", style: `width:${dose.pct}%;background:var(--${dose.statusCls})` }),
          ...dose.markers.map((m) => el("div", { class: "mark", title: m.label, style: `left:${m.pct}%` }))),
        el("div", { class: "note", text: `${COPY["nasa.career"]} · ${dose.markers.map((m) => m.label).join(" · ")}` }),
      );
    } else {
      parts.push(el("p", { class: "note", text: dose ? dose.effectiveText : copyFor(src, "panel.noData") }));
    }
    if (d.weather) {
      const b = weatherBanner(d.weather, src.now());
      parts.push(el("div", { class: "note", text: d.weather.status === "ok" && !d.weather.stale ? b.cachedText : b.title }));
    }
    c.body.replaceChildren(...parts);
  };
  return { node: c.node, update };
}
