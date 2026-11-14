"""Meal logging. The `food_log` table belongs to the H agent (H19); `MealStore` below is a
test fake for `Store.insert_meal` / `Store.meals_between`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hub.food.catalog import load_catalog
from hub.food.log import FoodError, FoodWriter, MealItem, MealRequest
from hub.ingest import Ingestor
from hub.store import Store

FIX = Path(__file__).parent / "fixtures" / "catalog_test.json"
T = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)


class MealStore(Store):
    def __init__(self, path):
        super().__init__(path)
        self.meals: list[dict] = []

    def insert_meal(self, crew, eaten_at, created_at, items):
        self.meals.append({"crew": crew, "eaten_at": eaten_at, "items": items})
        return len(self.meals)

    def meals_between(self, start, end, crew):
        return [m for m in self.meals if start < m["eaten_at"] <= end]


@pytest.fixture
def rig(tmp_path, clock):
    clock.set(T)
    store = MealStore(tmp_path / "h.db")
    ing = Ingestor(store, clock)
    w = FoodWriter(store, ing, load_catalog(FIX), clock, boot=1763121600)
    yield w, store
    store.close()


def meal(*items, crew="crew-a", eaten_at=None):
    return MealRequest(crew, [MealItem(f, s) for f, s in items], eaten_at)


MEAL_M = (("fx-bar", 2), ("fx-drink", 1))


def test_meal_readings(rig):
    w, store = rig
    res = w.log_meal(meal(*MEAL_M))
    assert len(res.readings) == 9
    assert res.not_reported == ["intake_vitd_ug"]
    vals = {}
    for ind, rid, dup in res.readings:
        r = store.get_reading(rid)
        vals[ind] = r.val
        assert not dup
        assert (r.node, r.src, r.dev, r.crew, tuple(r.q)) == (
            "food",
            "self",
            "catalog",
            "crew-a",
            ("ok",),
        )
        assert r.boot == 1763121600
    assert vals == pytest.approx(
        {"intake_kcal": 420.0, "intake_protein_g": 8.0, "intake_carb_g": 73.0,
         "intake_fat_g": 9.6, "intake_water_ml": 250.0, "intake_sodium_mg": 210.0,
         "intake_potassium_mg": 490.0, "intake_calcium_mg": 65.0, "intake_iron_mg": 1.85}
    )  # fmt: skip
    assert sorted(store.get_reading(rid).seq for _, rid, _ in res.readings) == list(range(1, 10))


def test_zero_is_reported(rig):
    w, store = rig
    res = w.log_meal(meal(("fx-drink", 1)))
    assert res.not_reported == []
    d = {i: store.get_reading(r).val for i, r, _ in res.readings}
    assert d["intake_vitd_ug"] == 0.0


def test_one_null_blocks_the_nutrient(rig):
    w, _ = rig
    res = w.log_meal(meal(("fx-drink", 1), ("fx-bar", 1)))
    assert "intake_vitd_ug" in res.not_reported
    assert "intake_vitd_ug" not in [i for i, _, _ in res.readings]


def test_eaten_at_dates_the_reading(rig):
    w, store = rig
    res = w.log_meal(meal(*MEAL_M, eaten_at=T - timedelta(hours=2)))
    for _, rid, _ in res.readings:
        r = store.get_reading(rid)
        assert r.measured_at == "2026-11-14T10:00:00.000Z"
        assert r.age_ms == 7_200_000


@pytest.mark.parametrize(
    ("req", "reason"),
    [
        (meal(), "empty_meal"),
        (meal(*[("fx-bar", 1)] * 21), "too_many_items"),
        (meal(("nope", 1)), "unknown_food:nope"),
        (meal(("fx-bar", 0)), "bad_servings:fx-bar"),
        (meal(("fx-bar", 20.5)), "bad_servings:fx-bar"),
        (meal(("fx-bar", 1), eaten_at=T + timedelta(seconds=61)), "bad_time"),
        (meal(("fx-bar", 1), eaten_at=T - timedelta(hours=48, minutes=1)), "too_old"),
        (meal(("fx-bar", 1), crew="crew-z"), "bad_crew"),
    ],
)
def test_errors(rig, req, reason):
    w, store = rig
    with pytest.raises(FoodError) as ei:
        w.log_meal(req)
    assert ei.value.reason == reason
    assert store.count("readings") == 0 and store.meals == []


def test_servings_20_parses(rig):
    w, _ = rig
    assert w.log_meal(meal(("fx-pinch", 20))).meal_id == 1


def test_two_meals_distinct_keys(rig):
    w, store = rig
    w.log_meal(meal(*MEAL_M))
    res = w.log_meal(meal(*MEAL_M))
    assert [d for _, _, d in res.readings] == [False] * 9
    assert sorted(store.get_reading(rid).seq for _, rid, _ in res.readings) == list(range(10, 19))


def test_meal_row_and_outbox(rig):
    w, store = rig
    w.log_meal(meal(*MEAL_M))
    assert store.meals[0]["items"] == [
        {"food_id": "fx-bar", "servings": 2}, {"food_id": "fx-drink", "servings": 1}]  # fmt: skip
    assert store.meals[0]["crew"] == "crew-a"
    out = store.outbox_after(0, 100)
    assert len(out) == 9 and all(o.kind == "reading" for o in out)
    assert all({"status", "rule_id", "escalate_to"} <= set(o.payload) for o in out)
