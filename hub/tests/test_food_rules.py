"""Shape and boundary tests for the food rules (M7), run on the approved real file (M1, D33)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hub.thresholds import SOURCE_KINDS, band_status, load_rules, rules_for

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data/food/thresholds_food.json"
# D33: waits for the H agent to add `nasa_doc` to SOURCE_KINDS; runs automatically after.
pytestmark = pytest.mark.skipif("nasa_doc" not in SOURCE_KINDS, reason="nasa_doc not in SOURCE_KINDS yet")
IDS = {
    "intake_sodium_max", "intake_sodium_floor", "intake_iron_max", "intake_water_floor",
    "intake_vitd_floor", "intake_calcium_floor", "intake_calcium_max",
}  # fmt: skip


@pytest.fixture(scope="module")
def rules():
    return {r.id: r for r in load_rules(REAL)}


def test_real_file_is_not_placeholder():
    rs = load_rules(REAL)
    assert len(rs) == 7
    for r in rs:
        assert "PLACEHOLDER" not in r.note and "PLACEHOLDER" not in r.source_ref


def test_food_rule_ids(rules):
    assert set(rules) == IDS
    for r in rules.values():
        want = "nasa_std" if r.id == "intake_vitd_floor" else "nasa_doc"
        assert r.source_kind == want and r.source_ref
        assert r.url.startswith("https://") and r.hours is None


def test_floor_rules_use_floor_window(rules):
    floors = {i for i, r in rules.items() if r.window == "sum_24h_floor"}
    assert floors == {i for i in IDS if i.endswith("_floor")}
    assert all(rules[i].window == "dose_24h" for i in IDS - floors)
    for i in floors:
        assert "20 h of logging" in rules[i].note


def test_notes_state_population_reference_and_history(rules):
    for r in rules.values():
        assert "not a personal target" in r.note
    assert "historical operating band" in rules["intake_sodium_max"].note
    assert rules["intake_iron_max"].act is None


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
