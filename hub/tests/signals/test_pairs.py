from datetime import timedelta

import pytest

from hub.signals.engine import evaluate
from hub.tests.signals.kit import END, TZ, lift_set, meal, night, one, put_ref, real_rig, ring_hr
from hub.timeutil import parse_iso

TODAY = END.date()  # 07:00 local is 10:00 UTC, the same date


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


def test_last_meal_vs_sleep_with_20_pairs_but_one_fixed_side_says_no_spread(rig):
    for d in range(22, 0, -1):
        meal(rig, END - timedelta(days=d) + timedelta(hours=9), 500)  # always 16:00 local
        night(rig, END - timedelta(days=d - 1), 8.5 - 0.3 * (d % 5))
    s = one(rig, "last_meal_vs_sleep")
    assert len(s.pairs) == 22 and s.method.n == 22
    assert s.headline_key == "signals.pair.noSpread" and s.state == "steady" and s.value is None


def test_last_meal_pairs_never_mix_replay_and_real(rig):
    for d in range(22, 0, -1):
        day = END - timedelta(days=d)
        meal(rig, day + timedelta(hours=9 + d % 5), 500)  # real meals, 16:00-20:00 local
        rig.put("intake_water_ml", 500, day + timedelta(hours=14), node="sim-1", dev="catalog",
                src="replay", crew="crew-a")  # a later replay meal, 21:00 local  # fmt: skip
        night(rig, END - timedelta(days=d - 1), 8.5 - 0.3 * (d % 5))
    s = one(rig, "last_meal_vs_sleep")
    assert len(s.pairs) == 22 and not s.replay
    assert [p[1] for p in s.pairs] == [16.0 + d % 5 for d in range(22, 0, -1)]
    assert all(i.src != "replay" for i in s.inputs)


def test_replay_nights_never_pair_with_real_meals(rig):
    for d in range(22, 0, -1):
        meal(rig, END - timedelta(days=d) + timedelta(hours=9 + d % 5), 500)
        rig.put("sleep_h", 7.0 + 0.1 * (d % 5), END - timedelta(days=d - 1), node="sim-1",
                dev="RING", src="replay", crew="crew-a")  # fmt: skip
    s = one(rig, "last_meal_vs_sleep")
    assert s.state == "not_enough_data" and not s.pairs and s.replay
    assert all(i.src == "replay" for i in s.inputs)


def _space_weather(rig, level, at, replay=False):
    if replay:
        put_ref(rig, "space_weather", level, at, node="sim-1", dev="DONKI", src="replay")
    else:
        put_ref(rig, "space_weather", level, at, node="nasa", dev="DONKI", src="nasa")


def test_space_weather_pairs_never_mix_replay_and_real(rig):
    for d in range(5, 0, -1):
        _space_weather(rig, 1, END - timedelta(days=d))
        _space_weather(rig, 5, END - timedelta(days=d) + timedelta(hours=1), replay=True)
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "space_weather_vs_sleep")
    assert len(s.pairs) == 5 and not s.replay and [p[1] for p in s.pairs] == [1] * 5
    assert all(i.src != "replay" for i in s.inputs)


def test_replay_nights_pair_only_with_replay_space_weather(rig):
    for d in range(5, 0, -1):
        _space_weather(rig, 1, END - timedelta(days=d))
        rig.put("sleep_h", 7.0, END - timedelta(days=d - 1), node="sim-1", dev="RING",
                src="replay", crew="crew-a")  # fmt: skip
    s = one(rig, "space_weather_vs_sleep")
    assert s.state == "not_enough_data" and not s.pairs and s.replay  # no replay level yet
    for d in range(5, 0, -1):
        _space_weather(rig, 4, END - timedelta(days=d) + timedelta(hours=1), replay=True)
    s = one(rig, "space_weather_vs_sleep")
    assert len(s.pairs) == 5 and s.replay and [p[1] for p in s.pairs] == [4] * 5
    assert all(i.src == "replay" for i in s.inputs)


def test_space_weather_day_is_the_days_highest_level(rig):
    for d in range(5, 0, -1):
        _space_weather(rig, 3, END - timedelta(days=d))
        _space_weather(rig, 1, END - timedelta(days=d) + timedelta(hours=2))  # lower, later
        night(rig, END - timedelta(days=d - 1), 7.0)
    s = one(rig, "space_weather_vs_sleep")
    assert [p[1] for p in s.pairs] == [3] * 5


def _training_days(rig, days=22):
    """Day d: one camera set at 18:00 local; then the night that ends at 07:00 the next day."""
    for d in range(days, 0, -1):
        w = 9.81 * (5 + d % 7)  # 5 + d % 7 kg.m per rep
        lift_set(rig, f"t-{d}", END - timedelta(days=d) + timedelta(hours=11), [w] * 3)
        ring_hr(rig, END - timedelta(days=d - 1), 1.0, 55.0 + (d - 1) % 7 + 0.5 * ((d - 1) % 3))


def test_training_vs_rest_hr_pairs_the_day_with_the_next_night(rig):
    _training_days(rig)
    s = one(rig, "training_vs_rest_hr")
    assert len(s.pairs) == 22 and s.method.n == 22 and not s.replay
    # day d's work (3 reps x (5 + d % 7)) with the resting HR of the night that ends on d + 1
    assert s.pairs[0][0] == str(TODAY - timedelta(days=22))
    assert s.pairs[0][1] == pytest.approx(3 * (5 + 22 % 7))
    assert s.pairs[0][2] == pytest.approx(55.0 + 21 % 7 + 0.5 * (21 % 3))
    assert s.headline_key == "signals.pair.rho" and s.state == "steady" and not s.can_trigger
    assert s.value.unit == "rho" and s.value.low <= s.value.estimate <= s.value.high
    cam = [i for i in s.inputs if i.src == "camera"]
    assert len(cam) == 1 and cam[0].n == 66  # 22 sets x 3 reps
    assert any(i.dev == "RING" and i.ind == "hr" for i in s.inputs)


def test_training_vs_rest_hr_ignores_a_replay_set(rig):
    _training_days(rig)
    before = one(rig, "training_vs_rest_hr").pairs
    lift_set(rig, "sim", END - timedelta(days=5) + timedelta(hours=12), [99.0 * 9.81] * 3,
             node="sim-1")  # fmt: skip
    s = one(rig, "training_vs_rest_hr")
    assert s.pairs == before and all(i.node != "sim-1" for i in s.inputs)


def test_replay_nights_never_pair_with_real_sets(rig):
    for d in range(22, 0, -1):
        lift_set(rig, f"t-{d}", END - timedelta(days=d) + timedelta(hours=11), [9.81 * d] * 3)
        end = END - timedelta(days=d - 1)
        for k in range(12, 0, -1):
            rig.put("hr", 55.0 + d % 7, end - timedelta(minutes=5 * k - 2), node="sim-1",
                    dev="RING", src="replay", crew="crew-a")  # fmt: skip
        rig.put("sleep_h", 1.0, end, node="sim-1", dev="RING", src="replay", crew="crew-a")
    s = one(rig, "training_vs_rest_hr")
    assert s.replay and not s.pairs and s.state == "not_enough_data"
    assert all(i.src == "replay" for i in s.inputs)


def _cabin_earth(rig, hours=30):
    earth, cabin = {}, {}
    for h in range(hours, 0, -1):
        at = END - timedelta(hours=h)
        earth[at], cabin[at] = 15 + (h % 6), 22 + 0.2 * (h % 6)
        put_ref(rig, "earth_temp", earth[at], at, node="earth-1", dev="WEATHER", src="ref")
        rig.put("cabin_temp", cabin[at], at)
    return earth, cabin


def test_cabin_vs_earth_lags_and_no_best_lag(rig):
    earth, cabin = _cabin_earth(rig)
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.value is None and [x["lag_h"] for x in s.detail["lags"]] == [0, 1, 2, 3]
    assert s.detail["lags"][0]["n"] == 30 and s.detail["lags"][0]["rho"] is not None
    assert [x["n"] for x in s.detail["lags"]] == [30, 29, 28, 27]
    assert all(x["key"] == "signals.pair.lag" for x in s.detail["lags"])
    assert s.method.n == 30  # the largest pair count over the lags (lag 0 here)
    # A row at lag h is (earth at t, cabin at t + h): the cabin follows the earth.
    for key, x, y, h in s.pairs:
        t = parse_iso(key)
        assert x == pytest.approx(earth[t]) and y == pytest.approx(cabin[t + timedelta(hours=h)])


def test_cabin_vs_earth_fixed_cabin_says_no_spread_per_lag(rig):
    for h in range(30, 0, -1):
        at = END - timedelta(hours=h)
        put_ref(rig, "earth_temp", 15 + (h % 6), at, node="earth-1", dev="WEATHER", src="ref")
        rig.put("cabin_temp", 22.0, at)
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.headline_key == "signals.pair.noSpread" and s.method.n == 30 and s.pairs
    assert all(x["rho"] is None and x["key"] == "signals.pair.lagNoSpread"
               for x in s.detail["lags"])  # fmt: skip


def test_cabin_vs_earth_few_hours_says_few(rig):
    _cabin_earth(rig, hours=10)
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.headline_key == "signals.pair.few" and s.method.n == 10
    assert all(x["key"] == "signals.pair.lagFew" for x in s.detail["lags"])


def test_cabin_vs_earth_never_mixes_replay_and_real(rig):
    earth, _ = _cabin_earth(rig)
    for t in earth:
        put_ref(rig, "earth_temp", 40.0, t, node="sim-1", dev="WEATHER", src="replay")
    s = one(rig, "cabin_vs_earth", crew=None)
    assert not s.replay and s.detail["lags"][0]["n"] == 30
    assert all(x == pytest.approx(earth[parse_iso(k)]) for k, x, _, _ in s.pairs)
    assert all(i.src != "replay" for i in s.inputs)


def test_replay_cabin_never_pairs_with_real_earth(rig):
    for h in range(30, 0, -1):
        at = END - timedelta(hours=h)
        put_ref(rig, "earth_temp", 15 + (h % 6), at, node="earth-1", dev="WEATHER", src="ref")
        rig.put("cabin_temp", 22 + 0.2 * (h % 6), at, node="sim-1", src="replay")
    s = one(rig, "cabin_vs_earth", crew=None)
    assert s.replay and not s.pairs and s.state == "not_enough_data"
    assert all(i.src == "replay" for i in s.inputs)


def test_a_failing_builder_leaves_the_others(rig, monkeypatch, caplog):
    from hub.signals import engine

    def boom(ctx, spec, crew):
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.BUILDERS, ("trend", "cabin"), boom)
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a"], at=END, tz=TZ)
    ids = {s.id for s in out}
    assert "cabin_temp_6h" not in ids and "cabin_rh_ttl" in ids and "boom" in caplog.text
