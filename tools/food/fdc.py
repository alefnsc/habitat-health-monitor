"""Search USDA FoodData Central and add one generic food to the catalogue (D44). Import time only.

    python -m tools.food.fdc search "<words>" [--limit 10]
    python -m tools.food.fdc add <fdc_id> --id <slug> --category <c> --serving-g <g> --serving-label "<text>"
        [--name "<text>"] [--fluid-ml 0] [--note "<text>"]

Only the Foundation and SR Legacy data types (generic foods, no brand names) are searched or added. The key is a
personal key in USDA_FDC_API_KEY (never DEMO_KEY), sent in a header; `python -m tools.vault run -- ...` can supply
it from the team's key vault. `add` appends one row to items.csv and one item to catalog.json and leaves the other
items unchanged. Without --serving-g it lists the food's FDC portions and stops. The hub reads the catalogue at
start-up and never calls the internet.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

try:
    import build_catalog as bc
except ImportError:  # run as python -m tools.food.fdc
    from tools.food import build_catalog as bc

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
DATA_TYPES = ["Foundation", "SR Legacy"]
ITEMS = Path("data/food/items.csv")
CATALOG = Path("data/food/catalog.json")
FIELDS = [
    "id", "fdc_id", "fdc_dataset", "name", "category", "serving_g", "serving_label", "serving_source",
    "fluid_ml_per_serving", "fluid_basis", "note",
]  # fmt: skip


def _key(env: Mapping[str, str]) -> str:
    key = env.get("USDA_FDC_API_KEY") or env.get("FDC_API_KEY")
    if not key or key == "DEMO_KEY":
        raise SystemExit(
            "set USDA_FDC_API_KEY to a personal key (DEMO_KEY is not allowed), "
            "for example with python -m tools.vault run -- python -m tools.food.fdc ..."
        )
    return key


def dump_catalog(cat: Mapping) -> str:
    """The catalogue as build_catalog.py writes it."""
    return json.dumps(cat, indent=2, ensure_ascii=False) + "\n"


def search(key: str, words: str, limit: int) -> list[dict]:
    body = {"query": words, "dataType": DATA_TYPES, "pageSize": limit}
    try:
        r = httpx.post(SEARCH_URL, json=body, headers={"X-Api-Key": key}, timeout=30)
    except httpx.HTTPError as e:
        raise SystemExit(f"FDC search failed: {type(e).__name__}") from None
    if r.status_code != 200:
        raise SystemExit(f"FDC search returned HTTP {r.status_code}")
    return r.json().get("foods", [])


def _portion(p: Mapping) -> str:
    unit = p.get("modifier") or (p.get("measureUnit") or {}).get("name") or ""
    text = " ".join(
        str(x)
        for x in (p.get("amount") or p.get("value") or "", unit, p.get("portionDescription") or "")
        if x
    )
    return f"{p.get('gramWeight', 0):g} g: {text}".rstrip(": ")


def add(args: argparse.Namespace, key: str, today: str) -> int:
    rows = bc.read_items(args.items)
    cat = json.loads(args.catalog.read_text(encoding="utf-8"))
    ids = {r.id for r in rows} | {i["id"] for i in cat["items"]}
    if args.id in ids:
        raise SystemExit(f"{args.id} is already in the catalogue")
    if any(r.fdc_id == args.fdc_id for r in rows) or any(
        i["fdc_id"] == args.fdc_id for i in cat["items"]
    ):
        raise SystemExit(f"FDC id {args.fdc_id} is already in the catalogue")
    src = bc.ApiSource(key)
    try:
        meta = src.meta(args.fdc_id)
    except KeyError:
        raise SystemExit(f"FDC id {args.fdc_id} not found") from None
    except bc.BuildError as e:
        raise SystemExit(str(e)) from None
    if meta["dataset"] not in bc.DATASETS:
        raise SystemExit(
            f"FDC id {args.fdc_id} is not a Foundation or SR Legacy food; only generic foods are used"
        )
    if args.serving_g is None or args.serving_label is None:
        print(
            f"{args.fdc_id} {meta['description']}: FDC portions (pick one for --serving-g and --serving-label):"
        )
        for p in src.food(args.fdc_id).get("foodPortions", []):
            print("  " + _portion(p))
        return 1
    if args.serving_g <= 0 or args.fluid_ml < 0:
        raise SystemExit("--serving-g must be above 0 and --fluid-ml at least 0")
    row = bc.ItemRow(
        id=args.id, fdc_id=args.fdc_id, fdc_dataset=meta["dataset"], name=args.name or meta["description"],
        category=args.category, serving_g=args.serving_g, serving_label=args.serving_label,
        serving_source="team-chosen", fluid_ml_per_serving=args.fluid_ml,
        fluid_basis="solid food, drinking fluid not counted" if args.fluid_ml == 0 else "team-chosen convention",
        note=args.note,
    )  # fmt: skip
    item = bc.build_item(row, src.get(args.fdc_id), meta)
    p = item["per100g"]
    if all(p[k] is None for k in ("kcal", "protein_g", "carb_g", "fat_g")):
        raise SystemExit(f"{args.id}: kcal, protein, carb and fat are all not reported")
    item["values_via"] = "FDC API"
    item["accessed_at"] = today
    cat["items"].append(item)
    with open(args.items, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writerow({
            **{k: getattr(row, k) for k in FIELDS},
            "serving_g": f"{row.serving_g:g}",
            "fluid_ml_per_serving": f"{row.fluid_ml_per_serving:g}",
        })  # fmt: skip
    args.catalog.write_text(dump_catalog(cat), encoding="utf-8")
    print(f"added {args.id} (FDC {args.fdc_id}, {meta['dataset']}); restart a demo hub to load it")
    return 0


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    today: str | None = None,
) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(prog="python -m tools.food.fdc", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="search Foundation and SR Legacy foods")
    s.add_argument("words")
    s.add_argument("--limit", type=int, default=10)
    a = sub.add_parser("add", help="add one food to items.csv and catalog.json")
    a.add_argument("fdc_id", type=int)
    a.add_argument("--id", required=True)
    a.add_argument("--category", required=True)
    a.add_argument("--serving-g", type=float)
    a.add_argument("--serving-label")
    a.add_argument("--name")
    a.add_argument("--fluid-ml", type=float, default=0.0)
    a.add_argument("--note", default="added from the FDC API")
    a.add_argument("--items", type=Path, default=ITEMS)
    a.add_argument("--catalog", type=Path, default=CATALOG)
    args = ap.parse_args(argv)
    key = _key(env)
    if args.cmd == "search":
        names = {"SR Legacy": "sr_legacy", "Foundation": "foundation"}
        for f in search(key, args.words, args.limit):
            print(
                f"{f.get('fdcId')}\t{names.get(f.get('dataType'), f.get('dataType'))}\t{f.get('description')}"
            )
        return 0
    return add(args, key, today or datetime.now(UTC).date().isoformat())


if __name__ == "__main__":
    raise SystemExit(main())
