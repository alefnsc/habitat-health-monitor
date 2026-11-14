"""M10: guidance texts for the food rules."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = {i["id"]: i for i in json.loads((ROOT / "data/guidance.json").read_text(encoding="utf-8"))}
RULES = json.loads((ROOT / "data/food/thresholds_food.json").read_text(encoding="utf-8"))
REVIEW = (ROOT / "docs/guidance-review.md").read_text(encoding="utf-8")
FOOD = {k: v for k, v in GUIDE.items() if v["rule_id"].startswith("intake_")}
FORBIDDEN = ["diagnos", "you have", "tablet", "pill", "capsule", "dose of", "milligram", "mg "]
ADVICE = ["should eat", "eat more", "eat less", "menu", "supplement", "meal plan"]


def test_every_food_status_has_text():
    want = {f"{r['id']}.{s}" for r in RULES for s in ("watch", "act") if r.get(s) is not None}
    assert len(want) == 10
    assert want == set(FOOD)


def test_food_escalation():
    for i in FOOD.values():
        assert i["escalate_to"] == ("self" if i["status"] == "watch" else "cmo"), i["id"]


def test_food_content_rules():
    for i in FOOD.values():
        for k in ("do_now", "tell"):
            assert len(i[k]) <= 160, i["id"]
            assert not any(w in i[k].lower() for w in FORBIDDEN), i["id"]
        assert i["risk_url"].endswith("?i=176"), i["id"]


def test_no_numbers_with_units():
    for i in FOOD.values():
        for k in ("do_now", "tell"):
            assert not re.search(r"\d\s*(mg|g|ml|mL|kcal|µg|ug)\b", i[k]), i["id"]


def test_no_meal_advice_and_says_whom_to_tell():
    for i in FOOD.values():
        text = (i["do_now"] + " " + i["tell"]).lower()
        assert not any(w in text for w in ADVICE), i["id"]
        assert "tell the cmo" in i["tell"].lower(), i["id"]


def test_matches_review():
    for i in FOOD.values():
        for k in ("do_now", "tell"):
            assert i[k] in REVIEW, i["id"]
