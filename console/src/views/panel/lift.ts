import { COPY } from "../../copy";
import type { RepsBody, Session, StoredRep } from "../../contract";
import { el } from "../../dom";
import { formatTimeUtc } from "../../format";
import { formatTrainingWork as formatWork } from "../../model/exercise";
import { placesWork } from "../../model/panel/places";
import { tiltLine } from "../../model/panel/tilt";
import { card } from "./common";
import { liveSource, type CardSource } from "./source";

export interface LiftData {
  session: Session | null;
  reps: RepsBody | null;
}

const cameraReps = (body: RepsBody | null): StoredRep[] =>
  (body?.pairs ?? []).map((p) => p.camera).filter((c): c is StoredRep => !!c && Number.isFinite(c.work_j));

/** Card 1: the latest camera set, one bar per rep. */
export function liftCard(src: CardSource = liveSource): { node: HTMLElement; update: (d: LiftData) => void } {
  const c = card("p-lift", "1", COPY["panel.lift"]);
  const update = ({ session, reps }: LiftData) => {
    const cams = cameraReps(reps);
    const tilt = tiltLine((reps?.pairs ?? []).filter((p) => !!p.camera && Number.isFinite(p.camera.work_j)));
    if (!session || !cams.length) {
      c.sub.textContent = "";
      c.body.replaceChildren(el("p", { class: "kv", text: COPY["panel.liftNone"] }), el("p", { class: "note", text: COPY["panel.liftNote"] }));
      return;
    }
    const ex = session.exercise ? COPY[`panel.ex.${session.exercise}`] : COPY["panel.liftSet"];
    c.sub.textContent = `${ex} · ${COPY["panel.liftMass"]} ${session.mass_kg} kg · ${formatTimeUtc(session.started_at)}`
      + (src.label ? ` · ${src.label}` : "");
    const total = cams.reduce((s, r) => s + r.work_j, 0);
    const top = Math.max(...cams.map((r) => r.work_j), 1e-9);
    const bars = el("div", { class: "bars", role: "img", "aria-label": `${cams.length} ${COPY["lanes.reps"]}` });
    const xs = el("div", { class: "bars-x" });
    for (const r of cams) {
      bars.append(el("div", { class: "bar", style: `height:${Math.max(2, (r.work_j / top) * 100)}%` },
        el("span", { text: r.work_j.toFixed(0) })));
      xs.append(el("span", { text: `${COPY["panel.rep"]} ${r.rep}` }));
    }
    c.body.replaceChildren(
      el("div", {}, el("span", { class: "big", text: formatWork(total) }), " ",
        el("span", { class: "kv", text: `${cams.length} ${COPY["lanes.reps"]} · ${COPY["badge.camera"]}` })),
      bars, xs,
      el("p", { class: "note", text: `${COPY["panel.liftNote"]} ${COPY["work.note"]}` }),
      ...(tilt ? [el("p", { class: "note tilt", text: tilt })] : []),
      ...(src.setNote ? [el("p", { class: "note", text: src.setNote })] : []),
    );
  };
  return { node: c.node, update };
}

/** Card 2: the latest rep's work estimate at Earth, Moon, Mars and space-station gravity. */
export function placesCard(src: CardSource = liveSource): { node: HTMLElement; update: (d: LiftData) => void } {
  const c = card("p-places", "2", COPY["panel.places"]);
  const update = ({ reps }: LiftData) => {
    const last = cameraReps(reps).at(-1) ?? null;
    const rows = placesWork(last);
    if (!last || !rows) {
      c.sub.textContent = "";
      c.body.replaceChildren(el("p", { class: "kv", text: COPY["panel.liftNone"] }), el("p", { class: "note", text: COPY["panel.placesNote"] }));
      return;
    }
    c.sub.textContent = `${COPY["panel.rep"]} ${last.rep} · ${COPY["badge.camera"]}` + (src.label ? ` · ${src.label}` : "");
    const top = Math.max(...rows.map((r) => r.j), 1e-9);
    const list = rows.map((r) => el("div", { class: "place" },
      el("div", {}, el("div", { text: COPY[`panel.place.${r.key}`] }), el("div", { class: "g", text: `${r.g} m/s²` })),
      el("div", { class: "track" }, el("div", { class: "fill", style: `width:${(r.j / top) * 100}%` })),
      el("div", { class: "j", text: r.key === "iss" ? `≈ ${formatWork(0)}` : formatWork(r.j) })));
    c.body.replaceChildren(...list,
      el("p", { class: "note", text: COPY["panel.issNote"] }),
      el("p", { class: "note", text: COPY["panel.placesNote"] }));
  };
  return { node: c.node, update };
}
