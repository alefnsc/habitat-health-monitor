import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.assess import coverage_ok, load_escalation
from hub.results import escalate_to_for
from hub.tests.helpers import FOOD_RULES, MAIN_RULES, T_F, Rig, T, hours, minutes


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


@pytest.fixture
def food(tmp_path, clock):
    return Rig(tmp_path, clock, rule_files=(MAIN_RULES, FOOD_RULES))


def by_rule(res, rid):
    return next(x for x in res if x.rule_id == rid)


def test_instant_rule(rig):
    res = rig.put("cabin_temp", 26.0)
    results = rig.store.results_for(res.stored.id)
    perf = by_rule(results, "cabin_performance_temp")
    assert (perf.status, perf.val, perf.unit, perf.source_kind) == ("watch", 26.0, "C", "nasa_std")
    assert (perf.guidance_id, perf.escalate_to, perf.crew) == (
        "cabin_performance_temp.watch", "cmo", None,
    )  # fmt: skip
    box = by_rule(results, "cabin_health_box_temp")
    assert (box.status, box.guidance_id, box.escalate_to) == (
        "ok", "cabin_health_box_temp.ok", "self",
    )  # fmt: skip
    assert by_rule(results, "t_temp_1h").status == "unknown"
    assert (res.results[0].status, res.results[0].rule_id) == ("watch", "cabin_performance_temp")


def test_mean_1h_window(rig):
    rig.put("cabin_temp", 40.0, T - minutes(70))
    rig.put("cabin_temp", 20.0, T - minutes(50))
    rig.put("cabin_temp", 24.0, T - minutes(30))
    r = rig.put("cabin_temp", 28.0, T)
    m = by_rule(rig.store.results_for(r.stored.id), "t_temp_1h")
    assert (m.val, m.status) == (24.0, "ok")
    r = rig.put("cabin_temp", 31.0, T + minutes(1))
    m = by_rule(rig.store.results_for(r.stored.id), "t_temp_1h")
    assert (m.val, m.status) == (25.75, "watch")


def test_mean_1h_coverage(rig):
    rig.put("cabin_temp", 24.0, T - minutes(30))
    r = rig.put("cabin_temp", 28.0, T)
    m = by_rule(rig.store.results_for(r.stored.id), "t_temp_1h")
    assert (m.val, m.status) == (26.0, "unknown")


def test_coverage_ok():
    cases = [("mean_1h", 2700, True), ("mean_1h", 2699, False), ("mean_7d", 86400, True),
             ("mean_7d", 86399, False), ("instant", 0, True), ("cumulative", 0, True),
             ("dose_24h", 0, True), ("sum_24h_floor", 72000, True),
             ("sum_24h_floor", 71999, False)]  # fmt: skip
    for w, s, want in cases:
        assert coverage_ok(w, s) is want


def test_flagged_excluded(rig):
    r = rig.put("cabin_temp", 28.0, T - minutes(50), q=["settling"])
    assert rig.store.results_for(r.stored.id) == []
    rig.put("cabin_temp", 20.0, T - minutes(49))
    r2 = rig.put("cabin_temp", 22.0, T)
    m = by_rule(rig.store.results_for(r2.stored.id), "t_temp_1h")
    assert m.val == 21.0


def test_ppco2_end_to_end(rig):
    last = None
    for i in range(12):
        at = T - minutes(55) + minutes(5 * i)
        rig.put("cabin_p", 1000.0, at)
        last = rig.put("cabin_co2", 4000, at)
    d = last.derived[0]
    res = rig.store.results_for(d.id)
    h1 = by_rule(res, "co2_1h")
    assert h1.val == pytest.approx(3.000248, abs=1e-6)
    assert (h1.status, h1.escalate_to) == ("act", "flight_surgeon")
    assert by_rule(res, "co2_7d").status == "unknown"


def test_cumulative_and_lt(rig):
    rig.put("sleep_h", 4, node="manual", crew="crew-a")
    r = rig.put("sleep_h", 5, node="manual", crew="crew-a", dev="manual")
    c = by_rule(rig.store.results_for(r.stored.id), "t_sleep_cum")
    assert (c.val, c.status) == (9.0, "ok")
    r = rig.put("sleep_h", 1, node="manual", crew="crew-a")
    c = by_rule(rig.store.results_for(r.stored.id), "t_sleep_cum")
    assert (c.val, c.status) == (10.0, "watch")


def test_body_window_per_crew(rig):
    rig.put("sleep_h", 4, node="manual", crew="crew-a")
    r = rig.put("sleep_h", 9, node="manual", crew="crew-b")
    assert by_rule(rig.store.results_for(r.stored.id), "t_sleep_cum").val == 9.0


def test_dose_24h_sum(rig):
    for val, at in ((5, T - hours(25)), (7, T - hours(23)), (11, T)):
        rig.put("hr", val, at)
    val, n, first = rig.store.window_aggregate("hr", T - hours(24), T, None, False, "sum")
    assert (val, n) == (18.0, 2)
    assert first == "2026-11-13T13:00:00.000Z"


def test_no_rule_unknown(rig):
    r = rig.put("cabin_p", 1000.0)
    (e,) = r.results
    res = rig.store.results_for(r.stored.id)
    assert len(res) == 1
    x = res[0]
    assert (x.status, x.rule_id, x.source_kind, x.guidance_id, x.escalate_to) == (
        "unknown", None, None, None, "self",
    )  # fmt: skip
    assert e.status == "unknown"


def test_ungated_inds(rig):
    for ind, val in (("motion", 0.2), ("load_raw", 120)):
        node = "exercise-1" if ind == "load_raw" else "vitals-1"
        r = rig.put(ind, val, node=node)
        assert rig.store.results_for(r.stored.id) == []


def test_hours_gate(rig):
    r = rig.put("cabin_lux", 100, T)
    assert by_rule(rig.store.results_for(r.stored.id), "t_lux_awake").status == "watch"
    night = T + hours(15)  # 2026-11-15T03:00Z = 00:00 local
    r = rig.put("cabin_lux", 100, night)
    assert rig.store.results_for(r.stored.id) == []
    assert r.results[0].status == "unknown" and r.results[0].rule_id is None


def test_escalation_from_guidance(tmp_path, clock):
    rig = Rig(tmp_path, clock, escalation={"cabin_performance_temp.watch": "self"})
    r = rig.put("cabin_temp", 26.0)
    res = rig.store.results_for(r.stored.id)
    assert by_rule(res, "cabin_performance_temp").escalate_to == "self"
    assert by_rule(res, "cabin_health_box_temp").escalate_to == "self"


def test_escalate_to_for():
    cases = [("ok", "cabin_temp", "self"), ("unknown", "cabin_temp", "self"),
             ("watch", "cabin_temp", "cmo"), ("act", "cabin_temp", "flight_surgeon"),
             ("watch", "hr", "cmo"), ("act", "hr", "flight_surgeon"),
             ("ok", "intake_sodium_mg", "self"), ("unknown", "intake_sodium_mg", "self"),
             ("watch", "intake_sodium_mg", "self"), ("act", "intake_sodium_mg", "cmo"),
             ("act", "body_mass", "flight_surgeon")]  # fmt: skip
    for st, ind, want in cases:
        assert escalate_to_for(st, ind) == want
    from hub.contract import INTAKE_INDS

    assert all(escalate_to_for("act", i) == "cmo" for i in INTAKE_INDS)


def test_intake_escalation_fallback(food, tmp_path, clock):
    r = food.put("intake_sodium_mg", 2400)
    assert by_rule(food.store.results_for(r.stored.id), "t_na_max").escalate_to == "self"
    r = food.put("intake_sodium_mg", 3500.1, crew="crew-b")
    assert by_rule(food.store.results_for(r.stored.id), "t_na_max").escalate_to == "cmo"
    out = [i for i in food.store.outbox_after(0, 100) if i.payload.get("id") == r.stored.id]
    assert out[0].payload["escalate_to"] == "cmo"
    over = Rig(tmp_path / "x", clock, (MAIN_RULES, FOOD_RULES), {"t_na_max.act": "flight_surgeon"})
    r = over.put("intake_sodium_mg", 3500.1)
    assert by_rule(over.store.results_for(r.stored.id), "t_na_max").escalate_to == "flight_surgeon"


def test_load_escalation(tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps([
        {"id": "co2_1h.act", "escalate_to": "flight_surgeon", "why": "x"},
        {"id": "hr_rest_high.watch", "escalate_to": "self"},
        {"id": "bad.watch", "escalate_to": "doctor"},
    ]))  # fmt: skip
    assert load_escalation(p) == {"co2_1h.act": "flight_surgeon", "hr_rest_high.watch": "self"}
    assert load_escalation(tmp_path / "none.json") == {}


def test_outbox_carries_worst_of(rig):
    rig.put("cabin_temp", 26.0)
    (item,) = rig.store.outbox_after(0, 10)
    p = item.payload
    assert (p["status"], p["rule_id"], p["source_kind"], p["escalate_to"]) == (
        "watch", "cabin_performance_temp", "nasa_std", "cmo",
    )  # fmt: skip


def test_two_files_loaded(settings, clock):
    s = replace(settings, thresholds_path=MAIN_RULES, food_thresholds_path=FOOD_RULES)
    with TestClient(create_app(s, clock=clock)) as c:
        ids = [r.id for r in c.app.state.assessor.rules]
        assert ids[-2:] == ["t_na_max", "t_na_floor"] and len(ids) == 10
    s = replace(
        settings, thresholds_path=MAIN_RULES, food_thresholds_path=settings.db_path.parent / "x"
    )
    with TestClient(create_app(s, clock=clock)) as c:
        assert len(c.app.state.assessor.rules) == 8
        m = {"v": 1, "node": "food", "boot": 1, "seq": 1, "age_ms": 0, "ind": "intake_sodium_mg",
             "val": 5, "unit": "mg", "src": "self", "dev": "catalog", "q": ["ok"]}  # fmt: skip
        e = c.post("/api/readings", json=m).json()["results"][0]
        assert (e["status"], e["rule_id"]) == ("unknown", None)


def test_intake_upper_boundaries(tmp_path, clock):
    got = []
    for i, v in enumerate((2300, 2300.1, 3500, 3500.1)):
        rig = Rig(tmp_path / str(i), clock, (MAIN_RULES, FOOD_RULES))
        r = rig.put("intake_sodium_mg", v, T_F)
        got.append(by_rule(rig.store.results_for(r.stored.id), "t_na_max").status)
    assert got == ["ok", "watch", "watch", "act"]


def test_rolling_24h_sum_intake(food):
    food.put("intake_sodium_mg", 1000, T_F - hours(25))
    food.put("intake_sodium_mg", 1200, T_F - hours(23))
    r = food.put("intake_sodium_mg", 100, T_F)
    m = by_rule(food.store.results_for(r.stored.id), "t_na_max")
    assert (m.val, m.status) == (1300.0, "ok")


def test_intake_per_crew(food):
    ra = food.put("intake_sodium_mg", 2000, T_F, crew="crew-a")
    rb = food.put("intake_sodium_mg", 1500, T_F, crew="crew-b")
    rn = food.put("intake_sodium_mg", 700, T_F, crew=None)
    v = lambda r: by_rule(food.store.results_for(r.stored.id), "t_na_max").val
    assert (v(ra), v(rb), v(rn)) == (2000.0, 1500.0, 700.0)


def test_floor_coverage(tmp_path, clock):
    a = Rig(tmp_path / "a", clock, (MAIN_RULES, FOOD_RULES))
    a.put("intake_sodium_mg", 900, T_F - hours(10))
    r = a.put("intake_sodium_mg", 700, T_F)
    m = by_rule(a.store.results_for(r.stored.id), "t_na_floor")
    assert (m.status, m.val) == ("unknown", 1600.0)
    b = Rig(tmp_path / "b", clock, (MAIN_RULES, FOOD_RULES))
    b.put("intake_sodium_mg", 900, T_F - hours(21))
    r = b.put("intake_sodium_mg", 700, T_F)
    assert by_rule(b.store.results_for(r.stored.id), "t_na_floor").status == "ok"


def test_floor_boundaries(tmp_path, clock):
    got = []
    for i, total in enumerate((1500, 1499.9, 500, 499.9)):
        rig = Rig(tmp_path / str(i), clock, (MAIN_RULES, FOOD_RULES))
        rig.put("intake_sodium_mg", 0.0, T_F - hours(21))
        r = rig.put("intake_sodium_mg", total, T_F)
        got.append(by_rule(rig.store.results_for(r.stored.id), "t_na_floor").status)
    assert got == ["ok", "watch", "watch", "act"]


def test_preview_matches_assess(food):
    r = food.put("intake_sodium_mg", 2400, T_F)
    stored = by_rule(food.store.results_for(r.stored.id), "t_na_max")
    assert (stored.val, stored.status) == (2400.0, "watch")
    pv = by_rule(food.assessor.preview("intake_sodium_mg", "crew-a", T_F), "t_na_max")
    assert (pv.val, pv.status) == (2400.0, "watch")


def test_preview_stores_nothing(food):
    food.put("intake_sodium_mg", 2400, T_F)
    before = (food.store.count("assessments"), food.store.count("outbox"), len(food.events))
    res = food.assessor.preview("intake_sodium_mg", "crew-a", T_F + hours(8))
    assert by_rule(res, "t_na_max").val == 2400.0
    assert by_rule(res, "t_na_floor").status == "unknown"
    after = (food.store.count("assessments"), food.store.count("outbox"), len(food.events))
    assert before == after


def test_preview_after_day_rolls(food):
    food.put("intake_sodium_mg", 2400, T_F)
    res = food.assessor.preview("intake_sodium_mg", "crew-a", T_F + hours(25))
    assert [(x.val, x.status) for x in res] == [(None, "unknown"), (None, "unknown")]


def test_preview_non_window_rule(rig):
    before = rig.store.count("assessments")
    res = rig.assessor.preview("cabin_temp", None, T)
    inst = [x for x in res if x.rule_id in ("cabin_performance_temp", "cabin_health_box_temp")]
    assert len(inst) == 2 and all((x.val, x.status) == (None, "unknown") for x in inst)
    assert rig.store.count("assessments") == before
