export const SCREENS = ["panel", "status", "entry", "history", "lanes", "exercise", "food", "nasa", "prompts", "body"] as const;
export type Screen = (typeof SCREENS)[number];

/** The screen named in the hash, or `fallback` (the panel in the console, the status board in the replay build). */
export function screenFromHash(hash: string, fallback: Screen = "panel"): Screen {
  const name = hash.replace(/^#\/?/, "").split("/")[0];
  return (SCREENS as readonly string[]).includes(name) ? (name as Screen) : fallback;
}
