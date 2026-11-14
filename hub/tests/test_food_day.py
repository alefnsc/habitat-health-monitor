"""Day totals against fakes for H7a's `Assessor.preview` and H19's `Store.meals_between`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.contract import parse_reading
from hub.food.day import food_day
from hub.food.references import load_references
from hub.food.routes import router
from hub.results import AssessmentResult
from hub.tests.helpers import msg
from hub.tests.test_food_log import MealStore

T = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
CREWS = ["crew-a", "crew-b", "crew-c"]
FLOOR = SimpleNamespace(id="intake_sodium_floor", ind="intake_sodium_mg", window="sum_24h_floor")
CAP = SimpleNamespace(id="intake_sodium_max", ind="intake_sodium_mg", window="dose_24h")


def res(rule_id, status, ind="intake_sodium_mg", crew="crew-a"):
    return AssessmentResult(
        id=0, reading_id=0, ind=ind, val=0.0, unit="mg", status=status, rule_id=rule_id,
        source_kind="nasa_std", source_ref="ref", guidance_id=None,
        escalate_to="self" if status != "act" else "cmo", measured_at="x", crew=crew,
    )  # fmt: skip


class FakeAssessor:
    def __init__(self, table):
        self.table, self.rules = table, [FLOOR, CAP]

    def preview(self, ind, crew, at):
        return self.table.get((ind, crew), [])


@pytest.fixture
def store(tmp_path):
    s = MealStore(tmp_path / "d.db")
    yield s
    s.close()


def put(store, ind, val, hours_ago, crew="crew-a", seq=[0]):  # noqa: B006
    seq[0] += 1
    unit = {"intake_sodium_mg": "mg", "intake_kcal": "kcal", "body_mass": "kg"}[ind]
    node = "manual" if ind == "body_mass" else "food"
    dev = "manual" if ind == "body_mass" else "catalog"
    r = parse_reading(msg(node=node, boot=7, seq=seq[0], ind=ind, val=val, unit=unit, src="self",
                          dev=dev, crew=crew))  # fmt: skip
    store.insert_reading(r, T - timedelta(hours=hours_ago))


def test_totals_sum_and_null(store):
    put(store, "intake_kcal", 420, 3)
    put(store, "intake_kcal", 420, 1)
    store.meals += [
        {"crew": "crew-a", "eaten_at": T - timedelta(hours=h), "items": []} for h in (3, 1)
    ]
    d = food_day(store, FakeAssessor({}), "crew-a", T, crews=CREWS, rules=[FLOOR, CAP])
    k = d["totals"]["intake_kcal"]
    assert (k["val"], k["meals_reporting"], k["meals_total"]) == (840.0, 2, 2)
    v = d["totals"]["intake_vitd_ug"]
    assert (v["val"], v["meals_reporting"], v["meals_total"], v["status"]) == (
        None,
        0,
        2,
        "unknown",
    )
    assert list(d["totals"]) == list(d["totals"])  # all ten present
    assert len(d["totals"]) == 10 and d["body_mass"] is None
    assert (
        d["window_start"] == "2026-11-13T12:00:00.000Z"
        and d["window_end"] == "2026-11-14T12:00:00.000Z"
    )


def test_window_edges_and_crew_filter(store):
    put(store, "intake_kcal", 100, 25)
    put(store, "intake_kcal", 200, 23)
    put(store, "intake_kcal", 50, 2, crew="crew-b")
    a = food_day(store, FakeAssessor({}), "crew-a", T, crews=CREWS)
    assert a["totals"]["intake_kcal"]["val"] == 200.0
    allc = food_day(store, FakeAssessor({}), None, T, crews=CREWS)
    assert allc["crew"] is None and allc["totals"]["intake_kcal"]["val"] == 250.0


def test_status_is_live_and_worst_of_crews(store):
    put(store, "intake_sodium_mg", 2400, 1, crew="crew-a")
    put(store, "intake_sodium_mg", 210, 1, crew="crew-b")
    ass = FakeAssessor({
        ("intake_sodium_mg", "crew-a"): [res("intake_sodium_max", "watch"), res("intake_sodium_floor", "unknown")],
        ("intake_sodium_mg", "crew-b"): [res("intake_sodium_max", "ok", crew="crew-b"), res("intake_sodium_floor", "unknown", crew="crew-b")],
    })  # fmt: skip
    t = food_day(store, ass, None, T, crews=CREWS, rules=ass.rules)["totals"]["intake_sodium_mg"]
    assert t["val"] == 2610.0 and t["status"] == "watch" and t["rule_id"] == "intake_sodium_max"
    only_b = food_day(store, ass, "crew-b", T, crews=CREWS, rules=ass.rules)
    assert only_b["totals"]["intake_sodium_mg"]["status"] == "ok"
    later = food_day(store, ass, "crew-a", T + timedelta(hours=25), crews=CREWS, rules=ass.rules)
    n = later["totals"]["intake_sodium_mg"]
    assert (n["val"], n["meals_reporting"], n["status"]) == (None, 0, "unknown")


def test_floor_judged(store):
    put(store, "intake_sodium_mg", 900, 1)
    unjudged = FakeAssessor(
        {
            ("intake_sodium_mg", "crew-a"): [
                res("intake_sodium_max", "ok"),
                res("intake_sodium_floor", "unknown"),
            ]
        }
    )
    judged = FakeAssessor({("intake_sodium_mg", "crew-a"): [res("intake_sodium_max", "ok"), res("intake_sodium_floor", "watch")]})  # fmt: skip
    r = [FLOOR, CAP]
    a = food_day(store, unjudged, "crew-a", T, crews=CREWS, rules=r)["totals"]
    assert a["intake_sodium_mg"]["floor_judged"] is False
    assert a["intake_iron_mg"]["floor_judged"] is None
    b = food_day(store, judged, "crew-a", T, crews=CREWS, rules=r)["totals"]
    assert b["intake_sodium_mg"]["floor_judged"] is True


def test_body_mass(store):
    put(store, "body_mass", 70, 5)
    assert food_day(store, FakeAssessor({}), "crew-a", T, crews=CREWS)["body_mass"] == 70.0


def _refs(tmp_path, **over):
    item = {"ind": "intake_iron_mg", "label": "Iron", "kind": "upper", "low": None, "high": 8,
            "unit": "mg", "value_text": "no more than 8 mg per day", "sex_note": None,
            "source_ref": "TEST", "url": "https://example.org", "has_rule": True}  # fmt: skip
    item.update(over)
    p = tmp_path / "r.json"
    p.write_text(
        json.dumps({"source": "test", "retrieved": "2026-11-14", "items": [item], "notes": []})
    )
    return p


def test_references_file(tmp_path):
    assert load_references(_refs(tmp_path))["items"][0]["ind"] == "intake_iron_mg"
    with pytest.raises(ValueError, match="intake_iron_mg"):
        load_references(_refs(tmp_path, kind="bogus"))


def test_routes_use_ctx(settings, clock, tmp_path):
    clock.set(T)
    s = MealStore(settings.db_path)
    app = create_app(settings, clock=clock, store=s)
    refs = _refs(tmp_path)
    from dataclasses import replace

    st = replace(settings, food_references_path=refs)
    app.state.ctx = SimpleNamespace(store=s, assessor=FakeAssessor({}), settings=st)
    app.include_router(router)
    with TestClient(app) as c:
        assert c.get("/api/food/day?crew=crew-a").status_code == 200
        assert c.get("/api/food/day?crew=nope").status_code == 422
        assert c.get("/api/food/references").json()["source"] == "test"
        assert c.get("/api/food/day?at=bad").json() == {"reason": "bad_time"}
    s.close()


def test_no_conversion_constants():
    root = Path(__file__).resolve().parents[1]
    for p in root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        text = p.read_text()
        assert "4.184" not in text and "4184" not in text


# real Assessor.preview (H7a) with the H agent's test food rules
def _real(store):
    from hub.assess import Assessor
    from hub.thresholds import load_rules

    rules = load_rules(Path(__file__).parent / "fixtures" / "thresholds_food_test.json")
    return Assessor(store, rules, tz="UTC")


def test_real_preview_status_and_floor(store):
    ass = _real(store)
    put(store, "intake_sodium_mg", 2400, 1)
    d = food_day(store, ass, "crew-a", T, crews=CREWS, rules=ass.rules)["totals"]["intake_sodium_mg"]
    assert d["status"] == "watch" and d["rule_id"] == "t_na_max"
    assert d["floor_judged"] is False  # first reading only 1 h old
    put(store, "intake_sodium_mg", 10, 21)
    d = food_day(store, ass, "crew-a", T, crews=CREWS, rules=ass.rules)["totals"]["intake_sodium_mg"]
    assert d["floor_judged"] is True
    assert d["status"] == "watch"


def test_real_preview_all_crew_and_after_roll(store):
    ass = _real(store)
    put(store, "intake_sodium_mg", 2400, 1, crew="crew-a")
    put(store, "intake_sodium_mg", 210, 1, crew="crew-b")
    t = food_day(store, ass, None, T, crews=CREWS, rules=ass.rules)["totals"]["intake_sodium_mg"]
    assert t["val"] == 2610.0 and t["status"] == "watch"
    only_b = food_day(store, ass, "crew-b", T, crews=CREWS, rules=ass.rules)
    assert only_b["totals"]["intake_sodium_mg"]["status"] != "watch"
    late = food_day(store, ass, "crew-a", T + timedelta(hours=25), crews=CREWS, rules=ass.rules)
    n = late["totals"]["intake_sodium_mg"]
    assert (n["val"], n["status"]) == (None, "unknown")
    iron = food_day(store, ass, "crew-a", T, crews=CREWS, rules=ass.rules)["totals"]["intake_iron_mg"]
    assert iron["status"] == "unknown" and iron["floor_judged"] is None
