import {
  asOfLabel, blackoutLabel, indicatorLabel, orderedKeys, silenceLabel, sourceKindLabel,
} from "./model";
import type { GuidanceItem } from "./replay";
import type { GroundView } from "./types";

const ARROW = "→";
const DASH = "—";

function esc(s: unknown): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

export function utcClock(ms: number): string {
  return new Date(ms).toISOString().slice(11, 19);
}

function fmtVal(v: number): string {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
}

/** Render the whole ground view. `nowMs` is the ground clock (wall clock live, replay clock in replay). */
export function render(
  root: HTMLElement,
  view: GroundView,
  nowMs: number,
  banner: string | null,
): void {
  const link = view.beacon?.link ?? null;
  const asOf = link ? asOfLabel(link.light_time_s, link.time_scale) : "Earth's view";
  const silence = silenceLabel(view.lastArrivalMs, nowMs);

  const linkPanel = link
    ? `<dl>
        <dt>Link</dt><dd>${esc(link.state)}</dd>
        <dt>One-way hold</dt><dd>${esc(view.beacon!.hold_s)} s</dd>
        <dt>Queue</dt><dd>Queue on the habitat: ${esc(link.queue_len)} (as last reported)</dd>
        <dt>In flight</dt><dd>${esc(view.beacon!.in_flight)}</dd>
        <dt>Blackout</dt><dd>${esc(blackoutLabel(link.last_blackout, view.beacon!.last_blackout_cause))}</dd>
        <dt>Items received</dt><dd>${view.received}</dd>
      </dl>`
    : `<p>No link report yet. Items received: ${view.received}</p>`;

  const rows = orderedKeys(view)
    .map((k) => {
      const e = view.latest.get(k)!;
      return `<tr class="${e.greyed ? "greyed" : ""}">
        <td>${esc(indicatorLabel(e.ind))}</td>
        <td>${esc(fmtVal(e.val))} ${esc(e.unit)}</td>
        <td class="status status-${esc(e.status)}">${esc(e.status)}</td>
        <td>${esc(sourceKindLabel(e.source_kind))}</td>
        <td>${esc(e.src)}</td>
        <td>${esc(e.crew ?? "habitat")}</td>
        <td>${esc(e.measured_at)}</td>
      </tr>`;
    })
    .join("");

  const alerts = view.alerts
    .map(
      (a) => `<li><strong class="status status-${esc(a.status)}">${esc(a.prev_status)} ${ARROW} ${esc(a.status)}</strong>
        ${esc(a.ind)} ${DASH} rule ${esc(a.rule_id ?? "n/a")} ${DASH} ${esc(a.crew ?? "habitat")}
        ${DASH} ${esc(a.measured_at)} ${DASH} escalate to ${esc(a.escalate_to ?? "n/a")}</li>`,
    )
    .join("");

  root.innerHTML = `
    ${banner ? `<p class="banner" role="status">${esc(banner)}</p>` : ""}
    <header>
      <h2>Earth's view</h2>
      <p class="asof">${esc(asOf)}</p>
      <p>T = ${utcClock(nowMs)} UTC ${silence ? `<span class="silence">${esc(silence)}</span>` : ""}</p>
    </header>
    <section aria-label="Link"><h2>Link</h2>${linkPanel}</section>
    <section aria-label="Readings"><h2>Readings</h2>
      <div class="table-scroll"><table><thead><tr><th>Indicator</th><th>Value</th><th>Status</th><th>Basis</th><th>Source</th><th>Crew</th><th>Measured</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    </section>
    <section aria-label="Alerts"><h2>Alerts</h2>${alerts ? `<ul>${alerts}</ul>` : "<p>No alerts received.</p>"}</section>`;
}

/** Read-only crew view for the public replay: guidance for every non-ok, unflagged reading. */
export function renderCrewView(
  root: HTMLElement,
  view: GroundView,
  guidance: GuidanceItem[] | null,
): void {
  const byId = new Map((guidance ?? []).map((g) => [g.id, g]));
  const items = orderedKeys(view)
    .map((k) => view.latest.get(k)!)
    .filter((e) => !e.greyed && (e.status === "watch" || e.status === "act"))
    .map((e) => {
      const g = byId.get(`${e.rule_id}.${e.status}`) ?? byId.get(`default.${e.status}`);
      const body = g
        ? `<p>${esc(g.do_now ?? "")}</p><p>${esc(g.tell ?? "")}</p>`
        : "<p>No guidance text published for this status.</p>";
      return `<li><strong class="status status-${esc(e.status)}">${esc(e.status)}</strong>
        ${esc(indicatorLabel(e.ind))} (${esc(fmtVal(e.val))} ${esc(e.unit)})${body}</li>`;
    })
    .join("");
  root.innerHTML = `<section aria-label="Crew view (replay)"><h2>Crew view (replay)</h2>
    ${items ? `<ul>${items}</ul>` : "<p>Nothing needs attention in this replay position.</p>"}
    <p>Read-only. This is not a diagnosis. Educational prototype, not a medical device.</p></section>`;
}
