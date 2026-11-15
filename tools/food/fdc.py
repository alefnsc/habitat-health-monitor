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
import io
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from hub.food.catalog import CatalogError, load_catalog

try:
    import build_catalog as bc
except ImportError:  # run as python -m tools.food.fdc
    from tools.food import build_catalog as bc

personal_key = bc.personal_key
SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
DATA_TYPES = ["Foundation", "SR Legacy"]
ITEMS = Path("data/food/items.csv")
CATALOG = Path("data/food/catalog.json")
FIELDS = [
    "id", "fdc_id", "fdc_dataset", "name", "category", "serving_g", "serving_label", "serving_source",
    "fluid_ml_per_serving", "fluid_basis", "note",
]  # fmt: skip


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Rule R5: no company or brand name in the catalogue. SR Legacy holds brand-named records in two ways: whole
# categories of chain and restaurant foods, and brand names written in capitals ("..., KELLOGG'S, ...").
BRAND_CATEGORIES = frozenset({"Fast Foods", "Restaurant Foods"})
CAPS_RUN = re.compile(r"[A-Z]{3,}")
NOT_BRANDS = frozenset({"USDA"})  # "(Includes foods for USDA's Food Distribution Program)"


def food_category(food: Mapping) -> str | None:
    """foodCategory is an object in a food record and a string in a search hit."""
    c = food.get("foodCategory")
    return c.get("description") if isinstance(c, Mapping) else c


def brand_reason(text: str, category: str | None = None) -> str | None:
    """Why a description or name looks brand-named, or None."""
    if category in BRAND_CATEGORIES:
        return f"category {category}"
    caps = [w for w in CAPS_RUN.findall(text) if w not in NOT_BRANDS]
    return f"capitalised name {caps[0]}" if caps else None


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


def _replace_text(path: Path, text: str) -> None:
    """Write `text` to `path` through a temp file in the same folder, keeping the file's mode."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _csv_row(row: bc.ItemRow) -> str:
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n").writerow({
        **{k: getattr(row, k) for k in FIELDS},
        "serving_g": f"{row.serving_g:g}",
        "fluid_ml_per_serving": f"{row.fluid_ml_per_serving:g}",
    })  # fmt: skip
    return buf.getvalue()


def _append_row(items: Path, row: bc.ItemRow) -> None:
    old = items.read_text(encoding="utf-8")
    _replace_text(items, old + ("" if old.endswith("\n") or not old else "\n") + _csv_row(row))


def _check_loads(cat: Mapping, folder: Path) -> None:
    """Refuse a catalogue the hub would not load (a bad file makes it skip the food feature)."""
    fd, tmp = tempfile.mkstemp(prefix=".catalog-check.", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dump_catalog(cat))
        load_catalog(Path(tmp))
    except CatalogError as e:
        raise SystemExit(f"the hub would not load the new catalogue: {e}") from None
    finally:
        Path(tmp).unlink(missing_ok=True)


def save(catalog: Path, items: Path, cat: Mapping, row: bc.ItemRow) -> None:
    """Catalogue first, then the items.csv row; if the row fails, the catalogue goes back."""
    _check_loads(cat, catalog.parent)
    old = catalog.read_text(encoding="utf-8")
    _replace_text(catalog, dump_catalog(cat))
    try:
        _append_row(items, row)
    except BaseException:
        _replace_text(catalog, old)
        raise


def _check_args(args: argparse.Namespace) -> None:
    if not SLUG.match(args.id):
        raise SystemExit(
            "--id must be lower-case letters and digits joined by single hyphens, e.g. lentils-dry"
        )
    if not args.category.strip():
        raise SystemExit("--category must not be blank")
    if args.serving_label is not None and not args.serving_label.strip():
        raise SystemExit("--serving-label must not be blank")


def add(args: argparse.Namespace, key: str, today: str) -> int:
    _check_args(args)
    try:
        rows = bc.read_items(args.items)
    except bc.BuildError as e:
        raise SystemExit(f"{args.items}: {e}") from None
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
    reason = brand_reason(meta["description"], food_category(src.food(args.fdc_id)))
    if reason is None and args.name:
        reason = brand_reason(args.name)
    if reason:
        raise SystemExit(
            f"FDC id {args.fdc_id} looks brand-named ({reason}); only generic foods without brand names are used"
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
    save(args.catalog, args.items, cat, row)
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
    key = personal_key(
        env, "for example with python -m tools.vault run -- python -m tools.food.fdc ..."
    )
    if args.cmd == "search":
        names = {"SR Legacy": "sr_legacy", "Foundation": "foundation"}
        hidden = 0
        for f in search(key, args.words, args.limit):
            if brand_reason(f.get("description") or "", food_category(f)):
                hidden += 1
                continue
            print(
                f"{f.get('fdcId')}\t{names.get(f.get('dataType'), f.get('dataType'))}\t{f.get('description')}"
            )
        if hidden:
            print(f"({hidden} brand-named hits hidden)")
        return 0
    return add(args, key, today or datetime.now(UTC).date().isoformat())


if __name__ == "__main__":
    raise SystemExit(main())
