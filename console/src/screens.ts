export const SCREENS = ["status", "entry", "history", "exercise", "food", "nasa", "prompts", "body"] as const;
export type Screen = (typeof SCREENS)[number];

export function screenFromHash(hash: string): Screen {
  const name = hash.replace(/^#\/?/, "").split("/")[0];
  return (SCREENS as readonly string[]).includes(name) ? (name as Screen) : "status";
}
