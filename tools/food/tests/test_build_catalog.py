"""Offline tests for the catalogue generator. Fixture values are test data, not food claims."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import build_catalog as bc
import httpx
import pytest
import respx

FIX = Path(__file__).parent / "fixtures"
BULK = FIX / "bulk"
ITEMS = FIX / "items_fixture.csv"
NOW = datetime(2026, 11, 14, 15, 0, 0, tzinfo=UTC)
TOOL = Path(bc.__file__)


def build(items: Path = ITEMS, **kw) -> dict:
    rows = bc.read_items(items)
    return bc.build_catalog(rows, bc.BulkSource([BULK]), NOW, generator="gen", **kw)


def test_energy_prefers_1008():
    assert bc.energy_kcal({1008: 350, 2047: 340}) == (350.0, "measured_1008")
    assert bc.energy_kcal({2047: 340, 2048: 338}) == (340.0, "atwater_general_2047")
    assert bc.energy_kcal({2048: 338}) == (338.0, "atwater_specific_2048")
    assert bc.energy_kcal({}) == (None, "measured_1008")


def test_null_stays_null():
    cat = build()
    powder = next(i for i in cat["items"] if i["id"] == "test-powder")
    assert powder["per100g"]["vitd_ug"] is None
    assert set(powder["per100g"]) == set(bc.PER100G_KEYS)
    grain = next(i for i in cat["items"] if i["id"] == "test-grain")
    assert grain["per100g"]["vitd_ug"] == 0.0


def test_nutrient_map():
    cat = build()
    grain = next(i for i in cat["items"] if i["id"] == "test-grain")
    p = grain["per100g"]
    assert p["kcal"] == 350.0 and grain["kcal_basis"] == "measured_1008"
    assert (p["protein_g"], p["carb_g"], p["fat_g"]) == (10.0, 70.0, 2.0)
    assert (p["sodium_mg"], p["potassium_mg"], p["calcium_mg"], p["iron_mg"]) == (5, 200, 20, 1.5)
    assert cat["nutrient_map"]["intake_vitd_ug"] == 1114


def test_no_water_density_guess():
    cat = build()
    drink = next(i for i in cat["items"] if i["id"] == "test-drink")
    assert drink["fluid_ml_per_serving"] == 240.0
    grain = next(i for i in cat["items"] if i["id"] == "test-grain")
    assert grain["fluid_ml_per_serving"] == 0.0 and "not counted" in grain["fluid_basis"]


def test_rejects_missing_fdc_id(tmp_path):
    bad = tmp_path / "items.csv"
    bad.write_text(
        ITEMS.read_text().splitlines()[0]
        + "\nghost,1,sr_legacy,Ghost,grain,10,10 g,team-chosen,0,solid,dry\n"
    )
    with pytest.raises(bc.BuildError, match="ghost"):
        build(bad)


def test_all_null_energy_and_macros_fails(tmp_path):
    bad = tmp_path / "items.csv"
    bad.write_text(
        ITEMS.read_text().splitlines()[0]
        + "\nnada,900005,sr_legacy,Nada,grain,10,10 g,team-chosen,0,solid,dry\n"
    )
    with pytest.raises(bc.BuildError, match="nada"):
        build(bad)


def test_atwater_only_and_warning():
    src = bc.BulkSource([BULK])
    rows = [
        bc.ItemRow("atw", 900004, "sr_legacy", "Atw", "grain", 10, "10 g", "team-chosen", 0.0, "s", "n")
    ]
    cat = bc.build_catalog(rows, src, NOW, generator="g")
    assert cat["items"][0]["kcal_basis"] == "atwater_general_2047"
    assert cat["items"][0]["per100g"]["kcal"] == 340.0


def test_deterministic():
    assert json.dumps(build(), sort_keys=False) == json.dumps(build(), sort_keys=False)


def test_top_level_fields():
    cat = build()
    assert cat["version"] == 1
    assert "CC0 1.0" in cat["licence"]
    assert cat["disclaimer"] and cat["generator"] == "gen"
    assert cat["synthetic"] is True and cat["label"].startswith("SYNTHETIC")
    assert cat["generated_at"] == "2026-11-14T15:00:00.000Z"
    assert [i["id"] for i in cat["items"]] == ["test-grain", "test-drink", "test-powder"]
    assert cat["items"][0]["fdc_description"] == "Test grain, dry"


def test_no_demo_key(monkeypatch, tmp_path):
    for val in (None, "DEMO_KEY"):
        env = {"PATH": "/usr/bin:/bin"}
        if val:
            env["USDA_FDC_API_KEY"] = val
        with respx.mock(assert_all_called=False) as router:
            route = router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(SystemExit) as ei:
                bc.main(
                    ["--items", str(ITEMS), "--api", "--out", str(tmp_path / "o.json")], env=env
                )
            assert "USDA_FDC_API_KEY" in str(ei.value)
            assert not route.called


def test_api_key_not_logged():
    key = "SECRETKEY123"
    with respx.mock() as router:
        router.route().mock(side_effect=httpx.ConnectError(f"boom https://x/?api_key={key}"))
        with pytest.raises(bc.BuildError) as ei:
            bc.ApiSource(key).get(900001)
    assert key not in str(ei.value)


def test_api_rate_limit():
    with respx.mock() as router:
        route = router.route().mock(return_value=httpx.Response(429))
        with pytest.raises(bc.BuildError, match="rate limited; wait an hour or use --bulk-dir"):
            bc.ApiSource("k").get(900001)
        assert route.call_count == 1


def test_api_source_parses():
    body = {
        "description": "Test grain, dry",
        "dataType": "SR Legacy",
        "foodNutrients": [
            {"nutrient": {"id": 1008}, "amount": 350},
            {"nutrient": {"id": 1114}},
        ],
    }
    with respx.mock() as router:
        route = router.route().mock(return_value=httpx.Response(200, json=body))
        src = bc.ApiSource("k")
        n = src.get(900001)
        assert route.calls[0].request.headers["x-api-key"] == "k"
        assert "k" not in str(route.calls[0].request.url)
    assert n[1008] == 350.0 and n.get(1114) is None
    assert src.meta(900001)["description"] == "Test grain, dry"
    assert src.meta(900001)["dataset"] == "sr_legacy"


def test_cli_bulk(tmp_path):
    out = tmp_path / "cat.json"
    r = subprocess.run(
        [sys.executable, "-I", str(TOOL), "--items", str(ITEMS), "--bulk-dir", str(BULK),
         "--out", str(out)],
        check=False, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text())
    assert len(d["items"]) == 3 and "build_catalog.py" in d["generator"]
    assert "test-grain" in r.stdout
