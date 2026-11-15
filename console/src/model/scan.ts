/** Pack codes on the habitat's own food packs (D44): the QR text is `hhm-food:<item-id>`. */
const PREFIX = "hhm-food:";

type Ids = { items: readonly { id: string }[] };

/** The catalogue food a scanned or typed pack code names, or null when it names none. */
export function parsePackCode(text: string, catalog: Ids): string | null {
  const t = text.trim();
  if (!t.startsWith(PREFIX)) return null;
  const id = t.slice(PREFIX.length);
  return catalog.items.some((i) => i.id === id) ? id : null;
}

/** The first catalogue food among the codes seen in one camera frame. */
export function firstKnownCode(texts: readonly string[], catalog: Ids): string | null {
  for (const t of texts) {
    const id = parsePackCode(t, catalog);
    if (id) return id;
  }
  return null;
}
