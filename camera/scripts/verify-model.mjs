// Checks that the committed pose model is the file whose SHA-256 is recorded next to it. Runs before `dev` and `build`.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public", "models");
const name = "pose_landmarker_lite.task";

let recorded;
try {
  recorded = readFileSync(join(dir, `${name}.sha256`), "utf8").trim().split(/\s+/)[0];
} catch {
  console.error(`verify-model: cannot read ${name}.sha256 in ${dir}`);
  process.exit(1);
}

let actual;
try {
  actual = createHash("sha256").update(readFileSync(join(dir, name))).digest("hex");
} catch {
  console.error(`verify-model: cannot read ${name} in ${dir}`);
  process.exit(1);
}

if (actual !== recorded) {
  console.error(`verify-model: ${name} does not match its recorded SHA-256.\n  recorded ${recorded}\n  actual   ${actual}`);
  process.exit(1);
}
console.log(`verify-model: ${name} ok (sha256 ${actual.slice(0, 12)}…)`);
