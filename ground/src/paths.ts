/** URL of the published replay file, given the Vite base path. */
export function replayUrl(base: string): string {
  const withSlash = base.endsWith("/") ? base : `${base}/`;
  return `${withSlash}replay.json`;
}

/** Base URL for API calls: same origin in replay mode, optional override when live. */
export function apiBase(source: "live" | "replay", envApi: string | undefined): string {
  if (source === "replay") return "";
  return envApi ?? "";
}
