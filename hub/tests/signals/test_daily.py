from datetime import timedelta

import pytest

from hub.tests.signals.kit import END, meal, one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_water_trend_skips_days_without_a_meal(rig):
    for d in range(14, 0, -1):
        if d % 5 == 0:
            continue  # no meal logged that day: no value, not zero
        meal(rig, END - timedelta(days=d), 1500 + 50 * (14 - d))
    s = one(rig, "water_14d")
    assert s.state == "notable" and s.headline_key == "signals.trend.up"
    # The window is (at - 14 d, at]: day 14 falls just outside, and days 10 and 5 have no meal.
    assert s.method.n == 11 and s.value.per == "day" and s.value.unit == "mL"


def test_water_trend_needs_three_quarters_of_the_days(rig):
    for d in range(9, 0, -1):
        meal(rig, END - timedelta(days=d), 1500)
    s = one(rig, "water_14d")
    assert s.state == "not_enough_data"
    assert (s.missing[0].key, s.missing[0].need, s.missing[0].have) == (
        "signals.missing.days",
        11,
        9,
    )


def test_body_mass_keeps_the_last_weigh_in_of_each_day(rig):
    for d in range(28, 0, -1):
        day = END - timedelta(days=d)
        # an earlier, mistyped entry that day, then the real weigh-in
        put_ref(rig, "body_mass", 30.0, day - timedelta(hours=1), node="manual", dev="manual",
                src="self", crew="crew-a")  # fmt: skip
        put_ref(rig, "body_mass", 80.0 + 0.05 * d, day, node="manual", dev="manual", src="self",
                crew="crew-a")  # fmt: skip
    s = one(rig, "body_mass_30d")
    assert s.headline_key == "signals.trend.down" and s.value.unit == "kg"
    assert s.value.estimate == pytest.approx(-0.05, abs=0.01)


def test_a_crew_less_meal_never_counts_for_a_crew(rig):
    for d in range(13, 0, -1):
        rig.put("intake_water_ml", 1500, END - timedelta(days=d), node="food", dev="catalog",
                src="self", crew=None)  # logged without a crew  # fmt: skip
    s = one(rig, "water_14d")
    assert s.state == "not_enough_data" and s.missing[0].have == 0 and not s.inputs
