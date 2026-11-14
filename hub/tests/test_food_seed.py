import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hub.assess import Assessor
from hub.contract import INTAKE_ORDER, parse_reading
from hub.food.catalog import load_catalog
from hub.food.day import food_day
from hub.food.seed import PLANS, _totals, generate_seed, load_seed_meals, seed_to_replay
from hub.ingest import Ingestor
from hub.sim import load_replay, rewrite
from hub.thresholds import load_rules

ROOT = Path(__file__).resolve().parents[2]
CAT = load_catalog(ROOT / "data/food/catalog.json")
FIT = json.loads((ROOT / "data/food/seed_crew_days.json").read_text())
FLAGS = json.loads((ROOT / "data/food/seed_flags.json").read_text())
T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def day_totals(doc, crew, block):
    lo, hi = 24 * (doc["blocks"] - 1 - block), 24 * (doc["blocks"] - block)
    meals = [m for m in doc["meals"] if m["crew"] == crew and lo <= m["t_minus_h"] < hi]
    return _totals(CAT, meals)


def test_label_and_determinism():
    a = generate_seed(CAT, seed=1, blocks=3, crews=["crew-a"], plan={})
    b = generate_seed(CAT, seed=1, blocks=3, crews=["crew-a"], plan={})
    assert a == b and a["label"].startswith("SYNTHETIC")
    assert FIT["label"].startswith("SYNTHETIC") and FLAGS["label"].startswith("SYNTHETIC")
    assert FIT == generate_seed(CAT, seed=FIT["seed"], blocks=3, crews=FIT["crew"], plan=PLANS["fit"])


def test_fit_crew_days():
    for crew in FIT["crew"]:
        for b in range(3):
            t = day_totals(FIT, crew, b)
            assert all(v is not None for v in t.values())
            assert 2000 <= t["intake_kcal"] <= 3200
            assert t["intake_sodium_mg"] <= 2300 and t["intake_iron_mg"] <= 8
            assert t["intake_water_ml"] >= 2100


def test_fit_flags():
    assert day_totals(FLAGS, "crew-b", 2)["intake_sodium_mg"] > 2300
    assert 2000 <= day_totals(FLAGS, "crew-c", 2)["intake_water_ml"] < 2100
    assert {a["scenario"] for a in FLAGS["adjustments"]} == {"sodium_watch", "water_floor_watch"}
    for crew in ("crew-a",):
        assert day_totals(FLAGS, crew, 2)["intake_sodium_mg"] <= 2300


@pytest.mark.parametrize("doc", [FIT, FLAGS])
def test_coverage_and_meal_shape(doc):
    for crew in doc["crew"]:
        assert max(m["t_minus_h"] for m in doc["meals"] if m["crew"] == crew) >= 60
    for m in doc["meals"]:
        assert 0 <= m["t_minus_h"] <= 72
        for it in m["items"]:
            assert it["food_id"] in CAT.items
            assert 0.5 <= it["servings"] <= 4 and it["servings"] * 2 == int(it["servings"] * 2)


@pytest.mark.parametrize("name", ["food-crew-days", "food-flags"])
def test_replay_valid_and_backdated(name):
    lines = load_replay(ROOT / f"data/replay/{name}.jsonl")
    assert [x.t_ms for x in lines] == sorted(x.t_ms for x in lines)
    ages = []
    for i, ln in enumerate(lines, 1):
        age = lines[-1].t_ms - ln.t_ms
        ages.append(age)
        _, payload = rewrite(ln, boot=1, seq=i, age_ms=age)
        r = parse_reading(payload, max_bytes=256)
        assert r.node == "sim-1" and r.src == "replay" and r.crew in FIT["crew"]
        assert r.dev == ("manual" if r.ind == "body_mass" else "catalog")
    assert ages == sorted(ages, reverse=True) and ages[-1] == 0


def test_body_mass_synthetic():
    lines = load_replay(ROOT / "data/replay/food-crew-days.jsonl")
    bm = [x.msg for x in lines if x.msg["ind"] == "body_mass"]
    assert sorted(m["crew"] for m in bm) == sorted(FIT["crew"])
    assert all(55 <= m["val"] <= 90 for m in bm)


def test_meal_rows_loaded(settings, clock):
    from hub.store import Store

    store = Store(settings.db_path)
    n = load_seed_meals(store, FIT, CAT, T)
    assert n == len(FIT["meals"])
    rows = store.meals_between(T - timedelta(hours=72), T, None)
    assert len(rows) == n and store.count("readings") == 0
    assert load_seed_meals(store, FIT, CAT, T) == 0
    store.close()


def test_day_after_seed(settings, clock):
    from hub.store import Store

    clock.set(T)
    store = Store(settings.db_path)
    ing = Ingestor(store, clock)
    rules = load_rules(ROOT / "data/food/thresholds_food.json")
    ass = Assessor(store, rules, tz="UTC")
    ing.assessor = ass
    load_seed_meals(store, FLAGS, CAT, T)
    lines = seed_to_replay(FLAGS, CAT)
    end = lines[-1].t_ms
    for i, ln in enumerate(lines, 1):
        _, payload = rewrite(ln, boot=1, seq=i, age_ms=end - ln.t_ms)
        assert ing.ingest_reading(payload, channel="http").reason is None
    d = food_day(store, ass, "crew-b", T, crews=settings.crews, rules=rules)
    assert d["totals"]["intake_kcal"]["meals_total"] > 0
    for ind in INTAKE_ORDER:
        t = d["totals"][ind]
        if t["val"] is not None:
            assert t["meals_reporting"] >= 1
    assert d["totals"]["intake_sodium_mg"]["status"] == "watch"
    c = food_day(store, ass, "crew-c", T, crews=settings.crews, rules=rules)
    assert c["totals"]["intake_water_ml"]["status"] in {"watch", "act"}
    assert c["totals"]["intake_water_ml"]["floor_judged"] is True
    store.close()
