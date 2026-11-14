import { getLink } from "../api";
import { COPY } from "../copy";
import type { LinkState, StatusEntry } from "../contract";
import { el } from "../dom";
import { formatValue, sourceKindLabel } from "../format";
import { escalationSteps, guidanceFor, whyFor } from "../model/guidance";
import { GUIDANCE } from "../model/guidanceData";
import { board } from "../state";

let link: LinkState | null = null;
export function setLinkState(l: LinkState): void {
  link = l;
}

const RANK: Record<string, number> = { ok: 0, unknown: 1, watch: 2, act: 3 };

// A tile may stand for two indicators (blood pressure): use the one with the worse status.
export function entryForTile(id: string): StatusEntry | null {
  const inds = id === "bp" ? ["bp_sys", "bp_dia"] : [id];
  const found = board.entries.filter((e) => inds.includes(e.ind));
  if (!found.length) return null;
  return found.reduce((a, b) => (RANK[b.status] > RANK[a.status] ? b : a));
}

export async function openGuidance(entry: StatusEntry, onHistory?: () => void): Promise<void> {
  document.getElementById("guidance-panel")?.remove();
  if (!link) {
    try {
      link = await getLink();
    } catch {
      /* link simulator not reachable: the chain says light time unknown */
    }
  }
  const g = guidanceFor(entry, GUIDANCE);
  const why = whyFor(entry.ind, GUIDANCE);
  const panel = el("aside", { id: "guidance-panel", class: `tile ${entry.status}`, role: "dialog", "aria-label": "Guidance", style: "position:fixed;right:16px;bottom:16px;max-width:420px;max-height:80vh;overflow:auto;z-index:10;cursor:default" });
  panel.append(
    el("strong", { text: formatValue(entry.ind, entry.val, entry.unit) }),
    el("div", { class: "footnote", text: `${entry.rule_id ?? COPY["kind.none"]} · ${sourceKindLabel(entry.source_kind)}${entry.source_kind === "nasa_std" && entry.source_ref ? ` ${entry.source_ref}` : ""}` }),
  );
  if (g.doNow) {
    panel.append(el("h2", { text: COPY["guide.doNow"] }), el("p", { text: g.doNow }));
    if (g.tell) panel.append(el("h2", { text: COPY["guide.tell"] }), el("p", { text: g.tell }));
    if (g.riskUrl) panel.append(el("a", { href: g.riskUrl, target: "_blank", rel: "noopener", text: g.riskTitle ?? COPY["guide.risk"] }));
  } else {
    panel.append(el("p", { text: COPY["guide.missing"] }));
  }
  if (why) panel.append(el("h2", { text: COPY["guide.why"] }), el("p", { text: why }));
  const chain = el("ol");
  for (const s of escalationSteps(entry, link)) chain.append(el("li", { text: s.text, ...(s.current ? { "aria-current": "step", style: "font-weight:700" } : {}) }));
  panel.append(chain, el("p", { class: "footnote", text: g.disclaimer }));
  const close = el("button", { type: "button", text: COPY["guide.close"] });
  close.addEventListener("click", () => panel.remove());
  panel.append(close);
  if (onHistory) {
    const hist = el("button", { type: "button", text: COPY["nav.history"] });
    hist.addEventListener("click", () => { panel.remove(); onHistory(); });
    panel.append(" ", hist);
  }
  document.body.append(panel);
}
