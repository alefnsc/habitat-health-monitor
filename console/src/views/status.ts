import { getStatus } from "../api";
import { COPY } from "../copy";
import { el } from "../dom";
import { chipSource } from "../format";
import { BOARD_LAYOUT, applySnapshot, buildTiles, type Tile } from "../model/status";
import { board } from "../state";
import { CREW, WEARER_NODES, currentCrew, setWearer } from "../crew";
import type { CrewId } from "../contract";

function chip(text: string, cls = ""): HTMLElement {
  return el("span", { class: `chip ${cls}`.trim(), text });
}

export function tileElement(t: Tile, showCrewChip: boolean, onClick?: (t: Tile) => void): HTMLElement {
  const n = el(
    "article",
    { class: `tile ${t.statusClass}`, tabindex: 0, "data-tile": t.id, "data-status": t.statusClass },
    el("div", { class: "title", text: t.title }),
    el("div", { class: "value", text: t.value }),
    el("div", { class: "status", text: t.statusLabel }),
  );
  const chips = el("div", { class: "chips" });
  if (t.srcLabel) chips.append(chip(t.srcLabel));
  if (t.sourceKindLabel) chips.append(chip(chipSource(t.sourceKindLabel, t.sourceRef)));
  if (t.devText) chips.append(chip(t.devText));
  for (const b of t.badges) chips.append(chip(b, "estimate"));
  for (const f of t.flags) chips.append(chip(f, "flag"));
  if (showCrewChip && t.crewChip) chips.append(chip(t.crewChip));
  n.append(chips);
  if (t.ageText) n.append(el("div", { class: "age", text: t.ageText }));
  if (onClick) {
    n.addEventListener("click", () => onClick(t));
    n.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") onClick(t);
    });
  }
  return n;
}

const lastWearer = new Map<string, CrewId>();

function wearerPanel(): HTMLElement {
  const wrap = el("section", { class: "wearer" }, el("h2", { text: COPY["crew.wearerTitle"] }));
  for (const node of WEARER_NODES) {
    const id = `wearer-${node}`;
    const sel = el("select", { id });
    sel.append(el("option", { value: "", text: "\u2014" }));
    for (const c of CREW) sel.append(el("option", { value: c.id, text: c.label }));
    sel.value = lastWearer.get(node) ?? "";
    const note = el("span", { class: "footnote", "aria-live": "polite" });
    if (lastWearer.has(node)) note.textContent = ` (${COPY["crew.wearerNote"]})`;
    sel.addEventListener("change", async () => {
      if (!sel.value) return;
      const r = await setWearer(node, sel.value as CrewId);
      if (r.ok) {
        lastWearer.set(node, sel.value as CrewId);
        note.textContent = ` (${COPY["crew.wearerNote"]})`;
      } else {
        note.textContent = ` ${r.error}`;
      }
    });
    wrap.append(el("div", { class: "row" }, el("label", { for: id, text: node }), el("div", {}, sel, note)));
  }
  return wrap;
}

export function renderStatus(root: HTMLElement, onTile?: (t: Tile) => void, live = true): () => void {
  const host = el("div");
  root.replaceChildren(host, ...(live ? [wearerPanel()] : []));
  const draw = () => {
    const tiles = buildTiles(board.entries, Date.now());
    const byId = new Map(tiles.map((t) => [t.id, t]));
    const showCrew = currentCrew() === null;
    host.replaceChildren();
    const groups: [string, { id: string }[]][] = [
      [COPY["status.vitals"], BOARD_LAYOUT.vitals],
      [COPY["status.supporting"], BOARD_LAYOUT.supporting],
      [COPY["status.cabin"], BOARD_LAYOUT.cabin],
    ];
    for (const [title, specs] of groups) {
      const grid = el("div", { class: "grid" });
      for (const s of specs) grid.append(tileElement(byId.get(s.id)!, showCrew, onTile));
      host.append(el("h2", { text: title }), grid);
    }
  };
  const unsub = board.subscribe(draw);
  const tick = setInterval(draw, 5000);
  draw();
  if (live) void loadBoard();
  return () => {
    unsub();
    clearInterval(tick);
  };
}

export async function loadBoard(): Promise<void> {
  try {
    const body = await getStatus(currentCrew() ?? undefined);
    board.replace(applySnapshot(body));
  } catch {
    /* the hub-lost banner covers this; keep the last values */
  }
}
