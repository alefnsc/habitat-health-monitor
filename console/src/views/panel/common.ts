import { COPY } from "../../copy";
import { el } from "../../dom";

/** A numbered card in the panel's reading order. */
export function card(area: string, step: string, title: string): { node: HTMLElement; sub: HTMLElement; body: HTMLElement } {
  const sub = el("span", { class: "sub" });
  const body = el("div");
  const node = el("section", { class: `card ${area}`, "aria-label": title },
    el("h3", {}, step ? el("span", { class: "step", text: step }) : null, el("span", { text: title }), sub), body);
  return { node, sub, body };
}

export const none = (): HTMLElement => el("p", { class: "note", text: COPY["panel.noData"] });

export function pill(status: string, label: string): HTMLElement {
  return el("span", { class: `pill ${status}`, text: label });
}
