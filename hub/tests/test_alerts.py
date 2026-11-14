from hub.tests.helpers import FOOD_RULES, MAIN_RULES, T_F, Rig, T, hours, minutes


def alerts_of(rig, rule_id):
    return [a for a in rig.alerts if a.rule_id == rule_id]


def test_alert_transitions(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    for i, v in enumerate((22.0, 26.0, 26.5, 22.0)):
        rig.put("cabin_temp", v, T + minutes(i))
    got = [(a.status, a.prev_status) for a in alerts_of(rig, "cabin_performance_temp")]
    assert got == [("watch", "ok"), ("ok", "watch")]
    items = [i for i in rig.store.outbox_after(0, 100) if i.kind == "alert"]
    perf = [i for i in items if i.payload["rule_id"] == "cabin_performance_temp"]
    assert len(perf) == 2
    assert set(perf[0].payload) == {
        "id", "ind", "status", "prev_status", "rule_id", "measured_at", "crew", "escalate_to",
    }  # fmt: skip
    emitted = [
        d for k, d in rig.events if k == "alert" and d["rule_id"] == "cabin_performance_temp"
    ]
    assert len(emitted) == 2


def test_first_assessment_watch_alerts(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    rig.put("cabin_temp", 26.0)
    (a,) = alerts_of(rig, "cabin_performance_temp")
    assert a.prev_status is None


def test_unknown_never_alerts(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    rig.put("cabin_temp", 24.0, T - minutes(50))
    rig.put("cabin_temp", 24.0, T - minutes(10))  # coverage 40 min: unknown
    rig.put("cabin_temp", 24.0, T)  # coverage 50 min: ok
    assert alerts_of(rig, "t_temp_1h") == []


def test_frame_and_outbox_order(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    rig.put("cabin_temp", 22.0, T)
    rig.events.clear()
    rig.put("cabin_temp", 26.0, T + minutes(1))
    assert [k for k, _ in rig.events] == ["assessment", "alert"]
    assert [i.kind for i in rig.store.outbox_after(0, 100)] == ["reading", "reading", "alert"]


def test_alerts_per_crew(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    rig.put("hr", 110, T, node="vitals-1", crew="crew-a")
    rig.put("hr", 60, T + minutes(1), crew="crew-b")
    hr_alerts = alerts_of(rig, "t_hr")
    assert [(a.crew, a.status) for a in hr_alerts] == [("crew-a", "watch")]
    rig.put("hr", 60, T + minutes(2), crew="crew-a")
    assert [(a.crew, a.status) for a in alerts_of(rig, "t_hr")][-1] == ("crew-a", "ok")
    assert len(alerts_of(rig, "t_hr")) == 2


def test_alert_id(tmp_path, clock):
    rig = Rig(tmp_path, clock)
    r = rig.put("cabin_temp", 26.0)
    res = [x for x in rig.store.results_for(r.stored.id) if x.rule_id == "cabin_performance_temp"]
    assert rig.alerts[0].id == res[0].id


def test_intake_alert_on_log(tmp_path, clock):
    rig = Rig(tmp_path, clock, (MAIN_RULES, FOOD_RULES))
    rig.put("intake_sodium_mg", 2400, T_F)
    (a,) = alerts_of(rig, "t_na_max")
    assert (a.status, a.prev_status, a.escalate_to, a.crew) == ("watch", None, "self", "crew-a")
    n = len(rig.alerts)
    rig.assessor.preview("intake_sodium_mg", "crew-a", T_F + hours(8))
    assert len(rig.alerts) == n
