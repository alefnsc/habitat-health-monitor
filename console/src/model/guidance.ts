import type { EscalateTo, Ind, LinkState, Status, StatusEntry } from "../contract";
import { COPY, DISCLAIMER } from "../copy";

export interface GuidanceItem {
  id: string;
  rule_id: string;
  status: string;
  do_now: string;
  tell: string;
  escalate_to: EscalateTo;
  risk_title: string;
  risk_url: string;
  why?: string;
}

const blank = (s: string | undefined) => (s === undefined || s === "" || s === "—" ? null : s);

export function guidanceFor(entry: Pick<StatusEntry, "guidance_id" | "status">, items: GuidanceItem[]) {
  const id = entry.guidance_id ?? (entry.status === "unknown" ? "default.unknown" : entry.status === "ok" ? "default.ok" : null);
  const item = id ? items.find((i) => i.id === id) : undefined;
  return {
    doNow: item ? blank(item.do_now) : null,
    tell: item ? blank(item.tell) : null,
    riskTitle: item ? blank(item.risk_title) : null,
    riskUrl: item ? blank(item.risk_url) : null,
    disclaimer: DISCLAIMER as "This is not a diagnosis.",
  };
}

export function whyFor(ind: Ind, items: GuidanceItem[]): string | null {
  return blank(items.find((i) => i.id === `default.${ind}`)?.why);
}

function span(s: number): string {
  const total = Math.round(s);
  if (total < 60) return `${total} s`;
  const m = Math.floor(total / 60);
  const r = total % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

export function formatLightTime(lightTimeS: number, timeScale: number): string {
  const base = `${span(lightTimeS)} one-way`;
  return timeScale === 1 ? base : `${base} (demo: ${span(lightTimeS / timeScale)})`;
}

export function escalationSteps(
  entry: { status: Status; escalate_to: EscalateTo },
  link: LinkState | null,
): { step: EscalateTo; text: string; current: boolean }[] {
  let fs = COPY["guide.fsUnknown"];
  if (link) {
    fs = `${COPY["guide.fs"]}: message arrives in ${formatLightTime(link.light_time_s, link.time_scale)}`;
    if (link.state === "unreachable") fs += `. ${COPY["guide.unreachable"]}`;
    else if (link.state === "blackout") fs += `. ${COPY["guide.blackout"]}`;
  }
  const cur = (s: EscalateTo) => entry.status !== "ok" && entry.escalate_to === s;
  return [
    { step: "self", text: COPY["guide.self"], current: cur("self") },
    { step: "cmo", text: COPY["guide.cmo"], current: cur("cmo") },
    { step: "flight_surgeon", text: fs, current: cur("flight_surgeon") },
  ];
}
