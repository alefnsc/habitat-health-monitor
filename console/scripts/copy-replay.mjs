// Copies the ground replay file next to the replay build as replay.json, and the synthetic exercise replay
// (the habitat panel's lift cards) as exercise-day.jsonl.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "..", "dist-replay");
mkdirSync(out, { recursive: true });
copyFileSync(resolve(here, "..", "..", "data", "ground", "ground-replay.json"), resolve(out, "replay.json"));
console.log("copy-replay: data/ground/ground-replay.json -> dist-replay/replay.json");
copyFileSync(resolve(here, "..", "..", "data", "replay", "exercise-day.jsonl"), resolve(out, "exercise-day.jsonl"));
console.log("copy-replay: data/replay/exercise-day.jsonl -> dist-replay/exercise-day.jsonl");
