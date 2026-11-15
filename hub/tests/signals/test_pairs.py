from datetime import timedelta

import pytest

from hub.signals.engine import evaluate
from hub.tests.signals.kit import END, TZ, meal, night, one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_last_meal_vs_sleep_few_pairs_shows_table_only(rig):
    for d in range(6, 0, -1):
        meal(rig, END - timedelta(days=d) + timedelta(hours=9), 500)  # 16:00 local
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "last_meal_vs_sleep")
    assert s.state == "steady" and s.headline_key == "signals.pair.few" and s.value is None
    assert len(s.pairs) == 6 and s.pairs[0][1] == pytest.approx(16.0)


def test_last_meal_vs_sleep_rho_at_20_pairs_is_never_notable(rig):
    for d in range(22, 0, -1):
        hour = 9 + (d % 5)  # meals 16:00-20:00 local
        meal(rig, END - timedelta(days=d) + timedelta(hours=hour), 500)
        night(rig, END - timedelta(days=d - 1), 8.5 - 0.3 * (d % 5))
    s = one(rig, "last_meal_vs_sleep")
    assert s.headline_key == "signals.pair.rho" and s.state == "steady"
    assert s.value.unit == "rho" and s.value.low <= s.value.estimate <= s.value.high
    assert not s.can_trigger


def test_space_weather_pairs_never_mix_replay_and_real(rig):
    for d in range(5, 0, -1):
        put_ref(
            rig, "space_weather", 1, END - timedelta(days=d), node="nasa", dev="DONKI", src="nasa"
        )
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "space_weather_vs_sleep")
    assert len(s.pairs) == 5 and not s.replay
    assert all(i.src != "replay" for i in s.inputs)


def test_cabin_vs_earth_lags_and_no_best_lag(rig):
    for h in range(30, 0, -1):
        at = END - timedelta(hours=h)
        put_ref(rig, "earth_temp", 15 + (h % 6), at, node="earth-1", dev="WEATHER", src="ref")
        rig.put("cabin_temp", 22 + 0.2 * (h % 6), at)
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.value is None and [x["lag_h"] for x in s.detail["lags"]] == [0, 1, 2, 3]
    assert s.detail["lags"][0]["n"] == 30 and s.detail["lags"][0]["rho"] is not None


def test_a_failing_builder_leaves_the_others(rig, monkeypatch, caplog):
    from hub.signals import engine

    def boom(ctx, spec, crew):
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.BUILDERS, ("trend", "cabin"), boom)
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a"], at=END, tz=TZ)
    ids = {s.id for s in out}
    assert "cabin_temp_6h" not in ids and "cabin_rh_ttl" in ids and "boom" in caplog.text
