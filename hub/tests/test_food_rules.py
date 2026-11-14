"""Shape and boundary tests for the food rules (M7).

The numbers in the fixture are PLACEHOLDERS from the planning table (NU8). They are not
approved: M1 (Science) verifies them and the operator approves the real file. Until then
`data/food/thresholds_food.json` holds no rules and intake readings are stored but unassessed.
Once the real file is approved, point RULES at it and delete the placeholder fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hub.thresholds import band_status, load_rules, rules_for

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data/food/thresholds_food.json"
PLACEHOLDER = ROOT / "tools/food/tests/fixtures/thresholds_food_placeholder.json"
IDS = {
    "intake_sodium_max", "intake_sodium_floor", "intake_iron_max", "intake_water_floor",
    "intake_vitd_floor", "intake_calcium_floor", "intake_calcium_max",
}  # fmt: skip


@pytest.fixture(scope="module")
def rules():
    return {r.id: r for r in load_rules(PLACEHOLDER)}


def test_real_file_loads_and_is_not_placeholder():
    rs = load_rules(REAL)
    for r in rs:
        assert "PLACEHOLDER" not in r.note and "PLACEHOLDER" not in r.source_ref
    assert {r.id for r in rs} <= IDS


def test_food_rule_ids(rules):
    assert set(rules) == IDS
    for r in rules.values():
        assert r.source_kind == "nasa_std" and r.source_ref
        assert r.url.startswith("https://") and r.hours is None


def test_floor_rules_use_floor_window(rules):
    floors = {i for i, r in rules.items() if r.window == "sum_24h_floor"}
    assert floors == {i for i in IDS if i.endswith("_floor")}
    assert all(rules[i].window == "dose_24h" for i in IDS - floors)
    for i in floors:
        assert "20 h of logging" in rules[i].note


def test_sodium_upper_boundaries(rules):
    r = rules["intake_sodium_max"]
    got = [band_status(r, x) for x in (2300, 2300.1, 3500, 3500.1)]
    assert got == ["ok", "watch", "watch", "act"]


def test_floor_boundaries(rules):
    na, water = rules["intake_sodium_floor"], rules["intake_water_floor"]
    assert [band_status(na, x) for x in (1500, 1499.9, 500, 499.9)] == [
        "ok", "watch", "watch", "act"]  # fmt: skip
    assert [band_status(water, x) for x in (2100, 2099.9, 2000, 1999.9)] == [
        "ok", "watch", "watch", "act"]  # fmt: skip
    assert [band_status(rules["intake_vitd_floor"], x) for x in (25, 24.9)] == ["ok", "watch"]
    assert [band_status(rules["intake_calcium_floor"], x) for x in (1000, 999.9)] == [
        "ok", "watch"]  # fmt: skip


def test_upper_boundaries_other(rules):
    assert [band_status(rules["intake_iron_max"], x) for x in (8, 8.1)] == ["ok", "watch"]
    assert [band_status(rules["intake_calcium_max"], x) for x in (2500, 2500.1)] == [
        "ok", "watch"]  # fmt: skip


def test_rules_for_calcium_has_floor_and_cap(rules):
    assert {r.id for r in rules_for(list(rules.values()), "intake_calcium_mg")} == {
        "intake_calcium_floor", "intake_calcium_max"}  # fmt: skip
