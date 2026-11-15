"""FoodData Central search and add (D44 P2). HTTP is mocked; fixture values are test data, not food claims."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import fdc
import httpx
import pytest
import respx

REPO = Path(__file__).resolve().parents[3]
KEY = "test-key-not-real"
ENV = {"USDA_FDC_API_KEY": KEY}
SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"
FOOD = "https://api.nal.usda.gov/fdc/v1/food/900042"

FOOD_BODY = {
    "fdcId": 900042,
    "description": "Test lentils, dry",
    "dataType": "SR Legacy",
    "foodNutrients": [
        {"nutrient": {"id": 1008}, "amount": 352.0},
        {"nutrient": {"id": 1003}, "amount": 24.6},
        {"nutrient": {"id": 1005}, "amount": 63.4},
        {"nutrient": {"id": 1004}, "amount": 1.06},
        {"nutrient": {"id": 1093}, "amount": 6.0},
        {"nutrient": {"id": 1114}},
    ],
    "foodPortions": [{"amount": 0.25, "modifier": "cup", "gramWeight": 48.0}],
}


@pytest.fixture
def data(tmp_path: Path) -> tuple[Path, Path]:
    items, cat = tmp_path / "items.csv", tmp_path / "catalog.json"
    shutil.copy(REPO / "data/food/items.csv", items)
    shutil.copy(REPO / "data/food/catalog.json", cat)
    return items, cat


def add_args(items: Path, cat: Path, *extra: str) -> list[str]:
    return ["add", "900042", "--id", "test-lentils-dry", "--category", "legume", "--serving-g", "48",
            "--serving-label", "1/4 cup dry", "--items", str(items), "--catalog", str(cat), *extra]  # fmt: skip


def test_search_asks_for_generic_data_types_with_the_key_in_a_header(capsys):
    hits = {
        "foods": [{"fdcId": 900042, "dataType": "SR Legacy", "description": "Test lentils, dry"}]
    }
    with respx.mock() as router:
        route = router.post(SEARCH).mock(return_value=httpx.Response(200, json=hits))
        assert fdc.main(["search", "lentils", "--limit", "5"], env=ENV) == 0
        req = route.calls[0].request
    body = json.loads(req.content)
    assert body == {"query": "lentils", "dataType": ["Foundation", "SR Legacy"], "pageSize": 5}
    assert req.headers["x-api-key"] == KEY and KEY not in str(req.url)
    out = capsys.readouterr().out
    assert "900042" in out and "sr_legacy" in out and "Test lentils, dry" in out
    assert KEY not in out


@pytest.mark.parametrize("env", [{}, {"USDA_FDC_API_KEY": "DEMO_KEY"}])
def test_no_personal_key_is_refused(env):
    with respx.mock() as router:
        with pytest.raises(SystemExit, match="USDA_FDC_API_KEY"):
            fdc.main(["search", "lentils"], env=env)
        assert not router.calls


def test_add_appends_one_item_and_leaves_the_rest_unchanged(data):
    items, cat = data
    old_items, old_cat = items.read_text(encoding="utf-8"), cat.read_text(encoding="utf-8")
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=FOOD_BODY))
        assert fdc.main(add_args(items, cat), env=ENV, today="2026-11-15") == 0
    new_items = items.read_text(encoding="utf-8")
    assert new_items.startswith(old_items) and new_items.count("\n") == old_items.count("\n") + 1
    assert new_items.endswith("test-lentils-dry,900042,sr_legacy,\"Test lentils, dry\",legume,48,1/4 cup dry,"
                              "team-chosen,0,\"solid food, drinking fluid not counted\",added from the FDC API\n")  # fmt: skip
    before, after = json.loads(old_cat), json.loads(cat.read_text(encoding="utf-8"))
    assert after["items"][:-1] == before["items"]
    assert {k: v for k, v in after.items() if k != "items"} == {
        k: v for k, v in before.items() if k != "items"
    }
    new = after["items"][-1]
    assert (
        new["id"] == "test-lentils-dry"
        and new["fdc_id"] == 900042
        and new["fdc_dataset"] == "sr_legacy"
    )
    assert new["fdc_description"] == "Test lentils, dry"
    assert new["values_via"] == "FDC API" and new["accessed_at"] == "2026-11-15"
    assert new["per100g"]["kcal"] == 352.0 and new["per100g"]["vitd_ug"] is None
    assert new["per100g"]["iron_mg"] is None  # not in the response: not reported, never 0


def test_added_catalogue_still_loads_in_the_hub(data):
    from hub.food.catalog import load_catalog, nutrients_for

    items, cat = data
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=FOOD_BODY))
        fdc.main(add_args(items, cat), env=ENV, today="2026-11-15")
    c = load_catalog(cat)
    assert nutrients_for(c.items["test-lentils-dry"], 1)["intake_kcal"] == pytest.approx(
        352.0 * 48 / 100
    )


def test_written_catalogue_keeps_the_committed_format():
    raw = (REPO / "data/food/catalog.json").read_text(encoding="utf-8")
    assert fdc.dump_catalog(json.loads(raw)) == raw


@pytest.mark.parametrize(
    ("extra", "why"),
    [(["--id", "white-rice-dry"], "already in the catalogue"), ([], None)],
)
def test_duplicates_are_refused(data, extra, why):
    items, cat = data
    args = add_args(items, cat, *extra)
    if why is None:  # same FDC id as an existing item
        args[1] = "169756"
        why = "FDC id 169756 is already"
    with respx.mock() as router:
        with pytest.raises(SystemExit, match=why):
            fdc.main(args, env=ENV)
        assert not router.calls


def test_branded_foods_are_refused(data):
    items, cat = data
    old = cat.read_text(encoding="utf-8")
    with respx.mock() as router:
        router.get(FOOD).mock(
            return_value=httpx.Response(200, json={**FOOD_BODY, "dataType": "Branded"})
        )
        with pytest.raises(SystemExit, match="Foundation or SR Legacy"):
            fdc.main(add_args(items, cat), env=ENV)
    assert cat.read_text(encoding="utf-8") == old


def test_without_a_serving_the_fdc_portions_are_listed(data, capsys):
    items, cat = data
    old = cat.read_text(encoding="utf-8")
    args = ["add", "900042", "--id", "test-lentils-dry", "--category", "legume",
            "--items", str(items), "--catalog", str(cat)]  # fmt: skip
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=FOOD_BODY))
        assert fdc.main(args, env=ENV) == 1
    assert "48 g: 0.25 cup" in capsys.readouterr().out
    assert cat.read_text(encoding="utf-8") == old


def test_unknown_fdc_id(data):
    items, cat = data
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(404))
        with pytest.raises(SystemExit, match="900042 not found"):
            fdc.main(add_args(items, cat), env=ENV)


def test_a_failed_catalogue_write_leaves_items_csv_unchanged(data, monkeypatch):
    items, cat = data
    old_items = items.read_text(encoding="utf-8")
    real = Path.write_text

    def fail_catalog(self, *a, **k):
        if self.name == "catalog.json":
            raise OSError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", fail_catalog)
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=FOOD_BODY))
        with pytest.raises(OSError):
            fdc.main(add_args(items, cat), env=ENV)
    assert items.read_text(encoding="utf-8") == old_items


def test_a_bad_items_csv_is_reported_without_a_traceback(data):
    items, cat = data
    items.write_text(
        items.read_text(encoding="utf-8").replace(",sr_legacy,", ",branded,", 1), encoding="utf-8"
    )
    with respx.mock(), pytest.raises(SystemExit, match="fdc_dataset must be"):
        fdc.main(add_args(items, cat), env=ENV)


def test_the_key_rule_is_shared_with_the_catalogue_builder():
    import build_catalog as bc

    assert fdc.personal_key is bc.personal_key


@pytest.mark.parametrize(
    "change",
    [
        {"foodCategory": {"description": "Fast Foods"}},
        {"foodCategory": {"description": "Restaurant Foods"}},
        {"description": "Cereals ready-to-eat, KELLOGG'S, Test flakes"},
        {"description": "McDONALD'S, Test burger"},
    ],
)
def test_brand_named_records_are_refused(data, change):
    items, cat = data
    old = cat.read_text(encoding="utf-8")
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json={**FOOD_BODY, **change}))
        with pytest.raises(SystemExit, match="brand"):
            fdc.main(add_args(items, cat), env=ENV)
    assert cat.read_text(encoding="utf-8") == old


def test_the_usda_programme_note_is_not_a_brand(data):
    items, cat = data
    body = {
        **FOOD_BODY,
        "description": "Test lentils, dry (Includes foods for USDA's Food Distribution Program)",
    }
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=body))
        assert fdc.main(add_args(items, cat), env=ENV, today="2026-11-15") == 0


def test_a_brand_named_display_name_is_refused(data):
    items, cat = data
    with respx.mock() as router:
        router.get(FOOD).mock(return_value=httpx.Response(200, json=FOOD_BODY))
        with pytest.raises(SystemExit, match="brand"):
            fdc.main(add_args(items, cat, "--name", "ACME lentils"), env=ENV)


def test_search_hides_brand_named_hits(capsys):
    hits = {
        "foods": [
            {
                "fdcId": 1,
                "dataType": "SR Legacy",
                "description": "Test oats, dry",
                "foodCategory": "Cereal Grains",
            },
            {
                "fdcId": 2,
                "dataType": "SR Legacy",
                "description": "Test burger",
                "foodCategory": "Fast Foods",
            },
            {"fdcId": 3, "dataType": "SR Legacy", "description": "Cereals, QUAKER, Test oats"},
        ]
    }
    with respx.mock() as router:
        router.post(SEARCH).mock(return_value=httpx.Response(200, json=hits))
        fdc.main(["search", "oats"], env=ENV)
    out = capsys.readouterr().out
    assert "Test oats, dry" in out
    assert "Test burger" not in out and "QUAKER" not in out
    assert "2 brand-named hits hidden" in out


def test_the_committed_catalogue_passes_the_brand_rule():
    cat = json.loads((REPO / "data/food/catalog.json").read_text(encoding="utf-8"))
    flagged = [
        i["id"]
        for i in cat["items"]
        if fdc.brand_reason(i["fdc_description"]) or fdc.brand_reason(i["name"])
    ]
    assert flagged == []
