// Canvas charts need real colour strings. They read the CSS variables from styles.css; the same values are the
// fallback where no stylesheet is loaded (tests).
const FALLBACK: Record<string, string> = {
  bg: "#111113", panel: "#18181b", raised: "#242428", line: "#404045", text: "#fafafa", "text-2": "#c9c9cf",
  muted: "#9f9fa8", ok: "#22c55e", watch: "#fb923c", act: "#f87171", unknown: "#a3a3a3", accent: "#a78bfa",
  series: "#60a5fa", "series-2": "#f472b6",
};

const cache = new Map<string, string>();

export function color(name: string): string {
  const hit = cache.get(name);
  if (hit) return hit;
  const v = typeof getComputedStyle !== "undefined" && typeof document !== "undefined"
    ? getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim()
    : "";
  if (v) cache.set(name, v); // stylesheet values are fixed for the page's life
  return v || FALLBACK[name] || "#888888";
}

/** "#rrggbb" plus an opacity, as an rgba() string for band fills. */
export function alpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}
