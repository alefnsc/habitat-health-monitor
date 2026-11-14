"""Food catalogue loader and per-meal nutrient maths (NU5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hub.contract import INTAKE_ORDER

# intake ind -> key in an item's per100g map. Fluid is not here: it is counted per serving.
PER100G_KEY: dict[str, str] = {
    "intake_kcal": "kcal",
    "intake_protein_g": "protein_g",
    "intake_carb_g": "carb_g",
    "intake_fat_g": "fat_g",
    "intake_sodium_mg": "sodium_mg",
    "intake_potassium_mg": "potassium_mg",
    "intake_calcium_mg": "calcium_mg",
    "intake_iron_mg": "iron_mg",
    "intake_vitd_ug": "vitd_ug",
}
PER100G_KEYS = tuple(PER100G_KEY.values())


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class FoodItem:
    id: str
    name: str
    category: str
    fdc_id: int
    serving_g: float
    serving_label: str
    fluid_ml_per_serving: float
    per100g: dict[str, float | None]


@dataclass(frozen=True)
class Catalog:
    items: dict[str, FoodItem]
    version: int
    raw: dict


def _num(item_id: str, field: str, v: object, *, positive: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CatalogError(f"item {item_id}: {field} must be a number")
    if v < 0 or (positive and v == 0):
        raise CatalogError(
            f"item {item_id}: {field} must be {'above 0' if positive else 'at least 0'}"
        )
    return float(v)


def _item(raw: dict) -> FoodItem:
    iid = raw.get("id") if isinstance(raw, dict) else None
    if not isinstance(iid, str) or not iid:
        raise CatalogError("an item has no id")
    for f in ("name", "category", "serving_label"):
        if not isinstance(raw.get(f), str) or not raw[f]:
            raise CatalogError(f"item {iid}: missing {f}")
    if not isinstance(raw.get("fdc_id"), int):
        raise CatalogError(f"item {iid}: fdc_id must be an integer")
    if "fluid_ml_per_serving" not in raw:
        raise CatalogError(f"item {iid}: missing fluid_ml_per_serving")
    per = raw.get("per100g")
    if not isinstance(per, dict):
        raise CatalogError(f"item {iid}: missing per100g")
    values: dict[str, float | None] = {}
    for k in PER100G_KEYS:
        if k not in per:
            raise CatalogError(f"item {iid}: per100g is missing {k}")
        values[k] = None if per[k] is None else _num(iid, f"per100g.{k}", per[k])
    return FoodItem(
        id=iid, name=raw["name"], category=raw["category"], fdc_id=raw["fdc_id"],
        serving_g=_num(iid, "serving_g", raw.get("serving_g"), positive=True),
        serving_label=raw["serving_label"],
        fluid_ml_per_serving=_num(iid, "fluid_ml_per_serving", raw["fluid_ml_per_serving"]),
        per100g=values,
    )  # fmt: skip


def load_catalog(path: Path) -> Catalog:
    path = Path(path)
    if not path.is_file():
        raise CatalogError(f"catalogue file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise CatalogError(f"{path}: invalid JSON: {e}") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise CatalogError(f"{path}: needs an items list")
    items: dict[str, FoodItem] = {}
    for r in raw["items"]:
        it = _item(r)
        if it.id in items:
            raise CatalogError(f"item {it.id}: duplicate id")
        items[it.id] = it
    return Catalog(items=items, version=int(raw.get("version", 1)), raw=raw)


def nutrients_for(item: FoodItem, servings: float) -> dict[str, float | None]:
    """Nutrients of `servings` servings, keyed by INTAKE_ORDER. None means not reported."""
    out: dict[str, float | None] = {}
    for ind in INTAKE_ORDER:
        if ind == "intake_water_ml":
            out[ind] = item.fluid_ml_per_serving * servings
            continue
        v = item.per100g[PER100G_KEY[ind]]
        out[ind] = None if v is None else v * item.serving_g / 100.0 * servings
    return out
