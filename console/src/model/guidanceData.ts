import type { GuidanceItem } from "./guidance";

// Bundled at build time; empty if data/guidance.json is missing (the panel then says so).
const files = import.meta.glob("../../../data/guidance.json", { eager: true, import: "default" }) as Record<string, GuidanceItem[]>;
export const GUIDANCE: GuidanceItem[] = Object.values(files)[0] ?? [];
