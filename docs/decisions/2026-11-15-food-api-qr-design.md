# Food lookups, one secret store and a pack scanner — design (D44)

Status: approved by the team owner, 2026-11-15 ~13:16 (UTC−03:00), build order "scanner first". Deadline day: the
video is recorded from 17:00 and the submission closes at 23:59.

The team owner's request: finish the FoodData Central integration, read its API key and the ring importer's app
credentials from the same existing key vault through the command line, and add a QR code scanner.

## 1. Premises (confirmed by the team owner)

- **FoodData Central is used at import time only.** A command-line tool searches it and adds chosen foods to the
  committed catalogue. The running hub never calls the internet; the habitat core stays usable with no link to
  Earth.
- **One secret store, the team's existing key vault.** It already holds the FoodData Central key and the ring
  vendor's app credentials. Today the runner hands out the FoodData Central key only. The ring importer keeps its
  `.env` app until the ring sign-in redirect is settled (D41 follow-up, a separate session); moving the ring to the
  vault is then one line in `.env`, with no code change.
- **The scanner reads QR codes on the habitat's own food packs**, not retail barcodes. No Branded records are added,
  so the "generic foods only, no brand names" rule in `docs/food-items.md` stands.

## 2. Parts and order

| Part | What | Order |
| --- | --- | --- |
| P3 | QR pack scanner on the console food screen, plus a printable label sheet | 1st (shown in the video) |
| P1 | Secret runner `python -m tools.vault` | 2nd |
| P2 | FoodData Central tool `python -m tools.food.fdc` (`search`, `add`) | 3rd |

P2 uses P1 for its key, but P2 also accepts `USDA_FDC_API_KEY` from the environment, so the parts can be tested
apart. If time runs out, P2 `search` is cut first, then P2 entirely; the cut parts stay here as later work.

## 3. P3: QR pack scanner

- **Pack code.** Each habitat food pack carries a QR code whose text is `hhm-food:<item-id>`, for example
  `hhm-food:white-rice-dry`. The same code is printed in plain text under the QR.
- **Labels.** `python tools/food/qr_labels.py --catalog data/food/catalog.json --out var/food-labels.html` writes a
  printable sheet: one QR per catalogue item, with the item name, serving label and code. `var/` is git-ignored. The
  QR encoder is `segno` (pure Python, BSD-3-Clause), in a new optional `labels` extra; the hub does not need it.
- **Console.** The food screen gets a "Scan pack" button next to the food picker:
  - it opens the camera and runs the browser's built-in `BarcodeDetector` for `qr_code` a few times a second;
  - a known code selects that food in the picker and closes the camera; the crew still sets servings, adds the item
    and logs the meal, so **a scan never logs anything by itself**;
  - an unknown or foreign code shows "This code is not a food in the catalogue." and keeps scanning;
  - a "Pack code" text field does the same for a typed code, for browsers without `BarcodeDetector` or a camera.
- **Offline.** The lookup is the catalogue the console already loaded from `/api/food/catalog`. No network call.
- **Code.** A pure function `parsePackCode` in `console/src/model/scan.ts`; the camera loop and the
  button live in the food view. All new text goes through `console/src/copy.ts`.

## 4. P1: secret runner

- **Config**, from the environment or the git-ignored `.env` (the environment wins):
  - `VAULT_NAME`: the key vault's name;
  - `VAULT_MAP`: comma-separated `ENV_NAME=secret-name` pairs, for example `USDA_FDC_API_KEY=<secret name>`.
  The vault and secret names stay out of the repository: they carry organisation and vendor names (rule R5).
- **`python -m tools.vault run -- <command> …`.** For each pair it runs
  `az keyvault secret show --vault-name <VAULT_NAME> --name <secret> --query value -o tsv`, puts the value into the
  child command's environment only, and runs the command. It exits with the command's exit code. A value is never
  printed, logged or written to disk; errors name the environment variable and `az`'s exit code only.
- **`python -m tools.vault check`.** For each pair it confirms the secret exists with `az keyvault secret list`
  (name, enabled, updated). That call never returns values.
- **Ring later.** Add `RING_CLIENT_ID=<secret>,RING_CLIENT_SECRET=<secret>` to `VAULT_MAP` and run
  `python -m tools.vault run -- python -m nodes.ring pull`. The importer reads the environment before `.env`
  already, so `nodes/ring/` does not change.
- **Rejected:** writing the values into `.env` (secrets on disk) and the key vault's Python SDK (new dependencies; the
  team owner asked for the command line).

## 5. P2: FoodData Central tool

- **`python -m tools.food.fdc search "<words>" [--limit 10]`.** Searches FoodData Central's Foundation and SR Legacy
  data types only, and prints FDC id, data type and description per hit. The key travels in the `X-Api-Key` header,
  never in the URL. `DEMO_KEY` is refused.
- **`python -m tools.food.fdc add <fdc_id> --id <slug> --category <c> --serving-g <g> --serving-label "<text>"
  [--fluid-ml 0] [--note "<text>"]`.**
  - It fetches that one food with the existing `ApiSource` and builds the item with the existing `build_item`.
  - It appends one row to `data/food/items.csv` and one item to `data/food/catalog.json`. The existing items are left
    unchanged byte for byte, so the values checked against the bulk files do not move.
  - The new item carries `fdc_id`, `fdc_dataset`, `fdc_description`, `values_via: "FDC API"` and `accessed_at`.
  - It refuses a duplicate id or FDC id, a data type other than Foundation or SR Legacy, and a missing key.
  - Without `--serving-g` it prints the food's FDC portions and stops, so the serving can be chosen from them.
- **Hub.** The hub reads the catalogue at start-up, so an added food appears after a restart of a demo hub. The live
  bench hub is never restarted for this.
- **No foods are added** by this work unless the team owner asks.

## 6. Rules kept

- Educational prototype, not a medical device. No calorie target, no meal plan, no "balance" or "deficit" wording.
  The honesty lint in `console/tests/copy.test.ts` keeps passing.
- UI text in English. No company or brand name in UI text or code; vendor names only in `DATA_SOURCES.md` (R5).
- No data of anyone under 18 (R8). The scanner selects a food; the crew is the console's current crew.
- No secret value is printed, logged or committed. Secrets are checked by name and metadata only.

## 7. Testing

- **Console (vitest):** `parsePackCode` (valid, unknown id, foreign text, whitespace, wrong prefix)
  and the copy lint.
- **Python (pytest):** the runner with a fake `az` (the value reaches the child; never captured output; missing
  config; `az` failure); `fdc search` and `fdc add` with mocked HTTP (respx): one item appended, others unchanged,
  Branded refused, duplicate refused, key only in the header; the label sheet holds one QR per item.
- **By hand:** the scanner in the browser against a demo hub with its own `HUB_DB` on another port, never the bench
  hub at 127.0.0.1:8000.

## 8. Later work

- Move the ring importer's app credentials to the vault (one `.env` line) once its sign-in redirect works.
- Retail barcodes (UPC/EAN) through Branded records: not chosen; it would reverse the generic-foods rule.
