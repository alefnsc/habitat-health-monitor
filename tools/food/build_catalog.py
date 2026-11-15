"""Build data/food/catalog.json from USDA FoodData Central (public domain, CC0 1.0).

Bulk CSV download first (no key). The API route is a fallback and needs a personal key in
USDA_FDC_API_KEY (never DEMO_KEY). Values are copied as published; a missing value stays null.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

FDC_NUMBERS: dict[str, int] = {
    "intake_kcal": 1008,
    "intake_protein_g": 1003,
    "intake_carb_g": 1005,
    "intake_fat_g": 1004,
    "intake_sodium_mg": 1093,
    "intake_potassium_mg": 1092,
    "intake_calcium_mg": 1087,
    "intake_iron_mg": 1089,
    "intake_vitd_ug": 1114,
}
# per100g key -> FDC nutrient id (the id column of the bulk nutrient table)
PER100G_IDS: dict[str, int] = {
    "kcal": 1008,
    "protein_g": 1003,
    "carb_g": 1005,
    "fat_g": 1004,
    "sodium_mg": 1093,
    "potassium_mg": 1092,
    "calcium_mg": 1087,
    "iron_mg": 1089,
    "vitd_ug": 1114,
}
PER100G_KEYS = tuple(PER100G_IDS)
ATWATER_GENERAL, ATWATER_SPECIFIC = 2047, 2048
WANTED_IDS = frozenset({*PER100G_IDS.values(), ATWATER_GENERAL, ATWATER_SPECIFIC})
DATASETS = {"sr_legacy", "foundation"}
LICENCE = "USDA FoodData Central, CC0 1.0; credit USDA FDC"
DISCLAIMER = (
    "Values are database values for generic foods, not NASA menu items and not measurements "
    "of the item eaten."
)
LABEL = "SYNTHETIC: generic database values, not real measurements and not NASA menu items"
DEFAULT_RELEASE = "SR Legacy 04/2018"
API_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"


class BuildError(Exception):
    pass


@dataclass(frozen=True)
class ItemRow:
    id: str
    fdc_id: int
    fdc_dataset: str
    name: str
    category: str
    serving_g: float
    serving_label: str
    serving_source: str
    fluid_ml_per_serving: float
    fluid_basis: str
    note: str


class NutrientSource(Protocol):
    def get(self, fdc_id: int) -> dict[int, float | None]: ...
    def meta(self, fdc_id: int) -> dict: ...


def read_items(path: Path) -> list[ItemRow]:
    rows: list[ItemRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["fdc_dataset"] not in DATASETS:
                raise BuildError(f"{r['id']}: fdc_dataset must be foundation or sr_legacy")
            serving = float(r["serving_g"])
            if serving <= 0:
                raise BuildError(f"{r['id']}: serving_g must be above 0")
            rows.append(
                ItemRow(
                    id=r["id"],
                    fdc_id=int(r["fdc_id"]),
                    fdc_dataset=r["fdc_dataset"],
                    name=r["name"],
                    category=r["category"],
                    serving_g=serving,
                    serving_label=r["serving_label"],
                    serving_source=r["serving_source"],
                    fluid_ml_per_serving=float(r["fluid_ml_per_serving"]),
                    fluid_basis=r["fluid_basis"],
                    note=r["note"],
                )
            )
    ids = [r.id for r in rows]
    if len(ids) != len(set(ids)):
        raise BuildError("duplicate item id in items.csv")
    return rows


def energy_kcal(nutrients: Mapping[int, float | None]) -> tuple[float | None, str]:
    for nid, basis in (
        (1008, "measured_1008"),
        (ATWATER_GENERAL, "atwater_general_2047"),
        (ATWATER_SPECIFIC, "atwater_specific_2048"),
    ):
        v = nutrients.get(nid)
        if v is not None:
            return float(v), basis
    return None, "measured_1008"


class BulkSource:
    """Reads the FDC CSV bulk download (one or more dataset folders)."""

    def __init__(self, dirs: Sequence[Path]):
        self._foods: dict[int, dict] = {}
        self._nutrients: dict[int, dict[int, float | None]] = {}
        for d in dirs:
            self._load(Path(d))

    def _load(self, d: Path) -> None:
        for name in ("food.csv", "food_nutrient.csv"):
            if not (d / name).is_file():
                raise BuildError(f"{d}: missing {name}")
        with open(d / "food.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self._foods[int(r["fdc_id"])] = {
                    "description": r["description"],
                    "dataset": r["data_type"].removesuffix("_food"),
                }
        with open(d / "food_nutrient.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                nid = int(r["nutrient_id"])
                if nid not in WANTED_IDS:
                    continue
                amt = r["amount"]
                self._nutrients.setdefault(int(r["fdc_id"]), {})[nid] = (
                    float(amt) if amt != "" else None
                )

    def get(self, fdc_id: int) -> dict[int, float | None]:
        if fdc_id not in self._foods:
            raise KeyError(fdc_id)
        return dict(self._nutrients.get(fdc_id, {}))

    def meta(self, fdc_id: int) -> dict:
        return self._foods[fdc_id]


class ApiSource:
    """FDC API fallback. The key travels in a header, never in the URL."""

    def __init__(self, key: str):
        self._key = key
        self._cache: dict[int, dict] = {}

    def _fetch(self, fdc_id: int) -> dict:
        if fdc_id in self._cache:
            return self._cache[fdc_id]
        try:
            r = httpx.get(
                API_URL.format(fdc_id=fdc_id), headers={"X-Api-Key": self._key}, timeout=30
            )
        except httpx.HTTPError as e:
            raise BuildError(f"FDC API request failed for {fdc_id}: {type(e).__name__}") from None
        if r.status_code == 429:
            raise BuildError("rate limited; wait an hour or use --bulk-dir")
        if r.status_code == 404:
            raise KeyError(fdc_id)
        if r.status_code != 200:
            raise BuildError(f"FDC API returned HTTP {r.status_code} for {fdc_id}")
        self._cache[fdc_id] = r.json()
        return self._cache[fdc_id]

    def get(self, fdc_id: int) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for fn in self._fetch(fdc_id).get("foodNutrients", []):
            nid = (fn.get("nutrient") or {}).get("id")
            if nid in WANTED_IDS:
                amt = fn.get("amount")
                out[nid] = float(amt) if amt is not None else None
        return out

    def food(self, fdc_id: int) -> dict:
        """The whole FDC food record (portions included)."""
        return self._fetch(fdc_id)

    def meta(self, fdc_id: int) -> dict:
        d = self._fetch(fdc_id)
        names = {"SR Legacy": "sr_legacy", "Foundation": "foundation"}
        return {
            "description": d.get("description", ""),
            "dataset": names.get(d.get("dataType"), "other"),
        }


def build_item(row: ItemRow, nutrients: Mapping[int, float | None], meta: Mapping) -> dict:
    per100g: dict[str, float | None] = {}
    for key, nid in PER100G_IDS.items():
        v = nutrients.get(nid)
        per100g[key] = None if v is None else float(v)
    kcal, basis = energy_kcal(nutrients)
    per100g["kcal"] = kcal
    return {
        "id": row.id,
        "name": row.name,
        "category": row.category,
        "fdc_id": row.fdc_id,
        "fdc_dataset": row.fdc_dataset,
        "fdc_description": meta["description"],
        "serving_g": row.serving_g,
        "serving_label": row.serving_label,
        "serving_source": row.serving_source,
        "fluid_ml_per_serving": row.fluid_ml_per_serving,
        "fluid_basis": row.fluid_basis,
        "per100g": per100g,
        "kcal_basis": basis,
        "note": row.note,
    }


def _iso(now: datetime) -> str:
    n = now.astimezone(UTC)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def build_catalog(
    rows: Sequence[ItemRow],
    source: NutrientSource,
    now: datetime,
    *,
    generator: str = "",
    fdc_release: str = DEFAULT_RELEASE,
    warnings: list[str] | None = None,
) -> dict:
    items = []
    for row in rows:
        try:
            nutrients = source.get(row.fdc_id)
            meta = source.meta(row.fdc_id)
        except KeyError:
            raise BuildError(f"{row.id}: FDC id {row.fdc_id} not found in the source") from None
        item = build_item(row, nutrients, meta)
        p = item["per100g"]
        if all(p[k] is None for k in ("kcal", "protein_g", "carb_g", "fat_g")):
            raise BuildError(f"{row.id}: kcal, protein, carb and fat are all not reported")
        if p["kcal"] is None and warnings is not None:
            warnings.append(f"{row.id}: no energy value reported")
        items.append(item)
    return {
        "version": 1,
        "synthetic": True,
        "label": LABEL,
        "generated_at": _iso(now),
        "generator": generator,
        "fdc_release": fdc_release,
        "licence": LICENCE,
        "disclaimer": DISCLAIMER,
        "nutrient_map": dict(FDC_NUMBERS),
        "items": items,
    }


def _report(cat: dict) -> str:
    def f(v: float | None) -> str:
        return "-" if v is None else f"{v:g}"

    lines = [f"{'id':34} {'kcal':>6} {'Na mg':>7} {'Fe mg':>6} {'D ug':>6}"]
    for i in cat["items"]:
        p = i["per100g"]
        lines.append(
            f"{i['id']:34} {f(p['kcal']):>6} {f(p['sodium_mg']):>7} {f(p['iron_mg']):>6} "
            f"{f(p['vitd_ug']):>6}"
        )
    return "\n".join(lines)


def personal_key(env: Mapping[str, str], hint: str) -> str:
    """A personal FDC key from USDA_FDC_API_KEY (or FDC_API_KEY); DEMO_KEY is refused."""
    key = env.get("USDA_FDC_API_KEY") or env.get("FDC_API_KEY")
    if not key or key == "DEMO_KEY":
        raise SystemExit(
            f"set USDA_FDC_API_KEY to a personal key (DEMO_KEY is not allowed), {hint}"
        )
    return key


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--bulk-dir", action="append", type=Path, default=[])
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--fdc-release", default=DEFAULT_RELEASE)
    args = ap.parse_args(argv)
    if bool(args.bulk_dir) == args.api:
        raise SystemExit("choose exactly one of --bulk-dir (repeatable) or --api")
    try:
        if args.api:
            source: NutrientSource = ApiSource(personal_key(env, "or use --bulk-dir"))
        else:
            source = BulkSource(args.bulk_dir)
        warnings: list[str] = []
        generator = "python tools/food/build_catalog.py " + " ".join(argv)
        cat = build_catalog(
            read_items(args.items),
            source,
            datetime.now(UTC),
            generator=generator,
            fdc_release=args.fdc_release,
            warnings=warnings,
        )
    except BuildError as e:
        raise SystemExit(f"build failed: {e}") from None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(_report(cat))
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
