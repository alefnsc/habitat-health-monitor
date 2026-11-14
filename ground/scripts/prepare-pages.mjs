// Copies the committed replay data into public/ before a Pages build.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";

mkdirSync("public", { recursive: true });
for (const [src, dst] of [
  ["../data/ground/ground-replay.json", "public/replay.json"],
  ["../data/guidance.json", "public/guidance.json"],
]) {
  if (existsSync(src)) copyFileSync(src, dst);
  else console.warn(`prepare-pages: ${src} not found, skipping`);
}
