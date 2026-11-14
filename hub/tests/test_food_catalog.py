import json
from pathlib import Path

import pytest

from hub.food.catalog import CatalogError, load_catalog, nutrients_for

FIX = Path(__file__).parent / "fixtures" / "catalog_test.json"


def test_nutrients_for():
    cat = load_catalog(FIX)
    bar = nutrients_for(cat.items["fx-bar"], 2)
    assert bar["intake_kcal"] == pytest.approx(320.0)
    assert bar["intake_protein_g"] == pytest.approx(8.0)
    assert bar["intake_carb_g"] == pytest.approx(48.0)
    assert bar["intake_fat_g"] == pytest.approx(9.6)
    assert bar["intake_sodium_mg"] == pytest.approx(160.0)
    assert bar["intake_potassium_mg"] == pytest.approx(240.0)
    assert bar["intake_calcium_mg"] == pytest.approx(40.0)
    assert bar["intake_iron_mg"] == pytest.approx(1.6)
    assert bar["intake_vitd_ug"] is None
    assert bar["intake_water_ml"] == 0.0
    drink = nutrients_for(cat.items["fx-drink"], 1)
    assert drink["intake_kcal"] == pytest.approx(100.0)
    assert drink["intake_carb_g"] == pytest.approx(25.0)
    assert drink["intake_sodium_mg"] == pytest.approx(50.0)
    assert drink["intake_iron_mg"] == pytest.approx(0.25)
    assert drink["intake_vitd_ug"] == 0.0
    assert drink["intake_water_ml"] == 250.0


def _mutate(tmp_path, fn):
    d = json.loads(FIX.read_text())
    fn(d)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(d))
    return p


@pytest.mark.parametrize(
    ("fn", "needle"),
    [
        (lambda d: d["items"][0].update(serving_g=0), "fx-bar: serving_g"),
        (
            lambda d: d["items"][0].pop("fluid_ml_per_serving"),
            "fx-bar: missing fluid_ml_per_serving",
        ),
        (lambda d: d["items"][1]["per100g"].pop("iron_mg"), "fx-drink: per100g is missing iron_mg"),
        (lambda d: d["items"][1].update(id="fx-bar"), "fx-bar: duplicate id"),
    ],
)
def test_catalog_load_errors(tmp_path, fn, needle):
    with pytest.raises(CatalogError, match=needle):
        load_catalog(_mutate(tmp_path, fn))


def test_missing_file(tmp_path):
    with pytest.raises(CatalogError, match="nope.json"):
        load_catalog(tmp_path / "nope.json")


def test_real_catalog_loads():
    root = Path(__file__).resolve().parents[2] / "data/food/catalog.json"
    cat = load_catalog(root)
    assert 28 <= len(cat.items) <= 32
    assert cat.raw["synthetic"] is True
