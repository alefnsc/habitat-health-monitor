import type { ThresholdRule } from "./history";

// Bundled at build time. The glob is empty if data/thresholds.json is missing, so the console still builds.
const files = import.meta.glob("../../../data/thresholds.json", { eager: true, import: "default" }) as Record<string, ThresholdRule[]>;
export const RULES: ThresholdRule[] = Object.values(files)[0] ?? [];
