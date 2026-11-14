type Child = Node | string | null | undefined | false;

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | boolean | number> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false) continue;
    if (k === "text") node.textContent = String(v);
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, String(v));
  }
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c);
  }
  return node;
}
