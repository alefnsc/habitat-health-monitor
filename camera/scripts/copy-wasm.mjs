// Copies the WASM runtime of the pinned @mediapipe/tasks-vision package into public/mediapipe/wasm, so the page
// serves it from its own origin. Runs before `dev` and `build`. The copy is git-ignored: it is not committed.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// npm workspaces hoist dependencies to the repo root, so walk up from this package looking for node_modules.
function findPackage(start) {
  for (let dir = start; ; dir = dirname(dir)) {
    const candidate = join(dir, "node_modules", "@mediapipe", "tasks-vision");
    if (existsSync(join(candidate, "package.json"))) return candidate;
    if (dirname(dir) === dir) return null;
  }
}

const pkg = findPackage(resolve(here, ".."));
if (!pkg || !existsSync(join(pkg, "wasm"))) {
  console.error("copy-wasm: @mediapipe/tasks-vision (with its wasm/ directory) not found: run `npm install` first.");
  process.exit(1);
}

const target = resolve(here, "..", "public", "mediapipe", "wasm");
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(join(pkg, "wasm"), target, { recursive: true });
console.log(`copy-wasm: ${join(pkg, "wasm")} -> ${target}`);
