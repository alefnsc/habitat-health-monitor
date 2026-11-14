"""Synthetic crew-day seed (M9). Everything here is generated, labelled SYNTHETIC, and
deterministic for a fixed seed. No real person's intake is used.

CLI:
  python -m hub.food.seed --out data/food/seed_crew_days.json \
      --replay data/replay/food-crew-days.jsonl --seed 20261114
  python -m hub.food.seed --flags --out data/food/seed_flags.json \
      --replay data/replay/food-flags.jsonl --seed 20261114
  python -m hub.food.seed --load-meals data/food/seed_crew_days.json   (hub stopped)
  python -m hub.food.seed --exercise data/replay/exercise-day.jsonl
  python -m hub.food.seed --load-session   (inserts the session row for that replay)
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hub.config import KNOWN_CREWS, load_settings
from hub.contract import INTAKE_ORDER, INTAKE_UNITS
from hub.food.catalog import Catalog, load_catalog, nutrients_for
from hub.sim import ReplayLine

LABEL = "SYNTHETIC: generated, not real people"
BLOCK_H = 24
DAY_OFFSETS = (3.0, 8.0, 14.0, 22.0)  # hours before the end of the block; 22 h keeps floors judged
MAX_TRIES = 20000
DRINKS = ("milk-powder-nonfat-d", "orange-juice-canned", "apple-juice-canned",
          "almond-milk-shelf-stable", "instant-tea-prepared")  # fmt: skip
SALTY = ("chicken-canned", "salmon-pink-canned", "sardines-canned-oil", "saltine-crackers",
         "peanut-butter-smooth", "tuna-light-canned-water")  # fmt: skip

Range = dict[str, tuple[float, float]]
FIT: Range = {
    "intake_kcal": (2000, 3200), "intake_sodium_mg": (0, 2300),
    "intake_iron_mg": (0, 8), "intake_water_ml": (2100, 1e9),
}  # fmt: skip
FLAG_SALT: Range = {
    "intake_kcal": (2000, 3600), "intake_sodium_mg": (2400, 3400),
    "intake_iron_mg": (0, 8), "intake_water_ml": (2100, 1e9),
}  # fmt: skip
FLAG_WATER: Range = {
    "intake_kcal": (2000, 3200), "intake_sodium_mg": (0, 2300),
    "intake_iron_mg": (0, 8), "intake_water_ml": (2000, 2090),
}  # fmt: skip
PLANS = {"fit": {}, "flags": {("crew-b", 2): ("sodium_watch", FLAG_SALT),
                              ("crew-c", 2): ("water_floor_watch", FLAG_WATER)}}  # fmt: skip


def _totals(catalog: Catalog, meals: list[dict]) -> dict[str, float | None]:
    tot: dict[str, float | None] = dict.fromkeys(INTAKE_ORDER, 0.0)
    for m in meals:
        for it in m["items"]:
            for ind, v in nutrients_for(catalog.items[it["food_id"]], it["servings"]).items():
                tot[ind] = None if v is None or tot[ind] is None else tot[ind] + v
    return tot


def _fits(tot: dict[str, float | None], rng_: Range) -> bool:
    return all(tot[i] is not None and lo <= tot[i] <= hi for i, (lo, hi) in rng_.items())


def _day(catalog: Catalog, r: random.Random, block: int, blocks: int, rng_: Range, salty: bool):
    solids = [i for i in catalog.items if i not in DRINKS]
    drinks = [i for i in DRINKS if i in catalog.items]
    for _ in range(MAX_TRIES):
        meals = []
        for off in DAY_OFFSETS:
            items = []
            for _k in range(r.randint(1, 3)):
                pool = SALTY if salty and r.random() < 0.6 else solids
                pool = [p for p in pool if p in catalog.items]
                items.append({"food_id": r.choice(pool), "servings": r.choice([0.5, 1, 1, 1.5, 2])})
            for _k in range(r.randint(1, 2)):
                items.append(
                    {"food_id": r.choice(drinks), "servings": r.choice([1, 1.5, 2, 2.5, 3])}
                )
            seen: dict[str, float] = {}
            for it in items:
                seen[it["food_id"]] = min(4.0, seen.get(it["food_id"], 0) + it["servings"])
            meals.append({
                "t_minus_h": off + BLOCK_H * (blocks - 1 - block),
                "items": [{"food_id": f, "servings": s} for f, s in seen.items()],
            })  # fmt: skip
        if _fits(_totals(catalog, meals), rng_):
            return meals
    raise RuntimeError(f"seed: no day found in {MAX_TRIES} tries for block {block}, range {rng_}")


def generate_seed(
    catalog: Catalog, *, seed: int, blocks: int, crews: list[str], plan: dict
) -> dict:  # fmt: skip
    r = random.Random(seed)
    meals: list[dict] = []
    adjustments: list[dict] = []
    for crew in crews:
        for b in range(blocks):
            name, rng_ = plan.get((crew, b), (None, FIT))
            if name:
                adjustments.append({"crew": crew, "block": b, "scenario": name})
            day = _day(catalog, r, b, blocks, rng_, salty=name == "sodium_watch")
            meals += [{"crew": crew, **m} for m in day]
    return {
        "label": LABEL,
        "generator": "python -m hub.food.seed",
        "seed": seed,
        "blocks": blocks,
        "crew": crews,
        "adjustments": adjustments,
        "body_mass_kg": {c: round(60 + 8 * r.random() + 5 * i, 1) for i, c in enumerate(crews)},
        "meals": meals,
    }


def seed_to_replay(doc: dict, catalog: Catalog) -> list[ReplayLine]:
    """Intake readings per meal, then one synthetic body_mass per crew at load time."""
    span_h = BLOCK_H * doc["blocks"]
    lines: list[tuple[int, int, ReplayLine]] = []
    for n, m in enumerate(doc["meals"]):
        t_ms = int((span_h - m["t_minus_h"]) * 3_600_000)
        tot = _totals(catalog, [m])
        for k, ind in enumerate(INTAKE_ORDER):
            if tot[ind] is None:
                continue
            msg = {
                "v": 1, "node": "sim-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": ind,
                "val": round(tot[ind], 2), "unit": INTAKE_UNITS[ind], "src": "replay",
                "dev": "catalog", "q": ["ok"], "crew": m["crew"],
            }  # fmt: skip
            lines.append((t_ms, n * 10 + k, ReplayLine(t_ms, "reading", msg)))
    lines.sort(key=lambda x: (x[0], x[1]))
    out = [x[2] for x in lines]
    end = span_h * 3_600_000
    for crew, kg in doc["body_mass_kg"].items():
        msg = {
            "v": 1, "node": "sim-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": "body_mass",
            "val": kg, "unit": "kg", "src": "replay", "dev": "manual", "q": ["ok"], "crew": crew,
        }  # fmt: skip
        out.append(ReplayLine(end, "reading", msg))
    return out


EXERCISE_SESSION = "demo-ex-1"
EXERCISE_MASS_KG = 10.0


def exercise_replay(seed: int) -> list[ReplayLine]:
    """One synthetic session of 8 camera reps (Earth gravity), replayed as node sim-1."""
    r = random.Random(seed)
    out = []
    for n in range(1, 9):
        t_ms = n * 4000
        msg = {
            "v": 1, "node": "sim-1", "boot": 1, "seq": 1, "age_ms": 0, "type": "rep",
            "session": EXERCISE_SESSION, "rep": n, "src": "camera",
            "peak_n": round(110 + 20 * r.random(), 1), "work_j": round(38 + 4 * r.random(), 1),
            "rom_m": round(0.38 + 0.02 * r.random(), 3), "g": 9.81, "mass_kg": EXERCISE_MASS_KG,
            "t0_ms": t_ms, "t1_ms": t_ms + 1800,
        }  # fmt: skip
        out.append(ReplayLine(t_ms, "rep", msg))
    return out


def load_exercise_session(store, now: datetime) -> bool:
    """The session row for the exercise replay (replay carries reps only)."""
    return store.insert_session(
        EXERCISE_SESSION, EXERCISE_MASS_KG, 9.81, "crew-a", now - timedelta(hours=1)
    )


def load_seed_meals(store, doc: dict, catalog: Catalog, now: datetime) -> int:
    """One food_log row per seed meal, dated now - t_minus_h. Writes no readings."""
    written = 0
    for m in doc["meals"]:
        eaten = now - timedelta(hours=m["t_minus_h"])
        existing = store.meals_between(eaten - timedelta(seconds=1), eaten, m["crew"])
        if any(e.crew == m["crew"] and e.items == m["items"] for e in existing):
            continue
        store.insert_meal(m["crew"], eaten, now, m["items"])
        written += 1
    return written


def _write_replay(path: Path, lines: list[ReplayLine]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(
            json.dumps({"t_ms": ln.t_ms, "kind": ln.kind, "msg": ln.msg}, separators=(",", ":"))
            + "\n"
            for ln in lines
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--replay", type=Path)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--flags", action="store_true")
    ap.add_argument("--catalog", type=Path)
    ap.add_argument("--load-meals", type=Path)
    ap.add_argument("--exercise", type=Path, help="write the exercise replay file here")
    ap.add_argument("--load-session", action="store_true", help="insert the exercise session row")
    a = ap.parse_args(argv)
    settings = load_settings(os.environ)
    catalog = load_catalog(a.catalog or settings.food_catalog_path)
    if a.exercise:
        _write_replay(a.exercise, exercise_replay(a.seed))
        return 0
    if a.load_session:
        from hub.store import Store

        store = Store(settings.db_path)
        print("inserted" if load_exercise_session(store, datetime.now(UTC)) else "already there")
        store.close()
        return 0
    if a.load_meals:
        from hub.store import Store

        doc = json.loads(a.load_meals.read_text(encoding="utf-8"))
        store = Store(settings.db_path)
        n = load_seed_meals(store, doc, catalog, datetime.now(UTC))
        store.close()
        print(f"wrote {n} meal rows")
        return 0
    if not a.out:
        ap.error("--out is required")
    plan = PLANS["flags" if a.flags else "fit"]
    doc = generate_seed(catalog, seed=a.seed, blocks=3, crews=list(KNOWN_CREWS), plan=plan)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    if a.replay:
        _write_replay(a.replay, seed_to_replay(doc, catalog))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
