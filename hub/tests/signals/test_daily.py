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
    # The window is the 14 complete local days before today; days 10 and 5 have no meal.
    assert s.method.n == 12 and s.value.per == "day" and s.value.unit == "mL"


def test_water_counts_14_complete_local_days_and_sums_each_one(rig):
    for d in range(15, 0, -1):
        day = END - timedelta(days=d)  # 07:00 local
        meal(rig, day - timedelta(hours=1), 600 + 10 * (15 - d))  # 06:00 local
        meal(rig, day + timedelta(hours=2), 900 + 10 * (15 - d))  # 09:00 local
    meal(rig, END + timedelta(minutes=30), 5000)  # today, 07:30 local: the day is still open
    s = one(rig, "water_14d")  # at 08:00 local
    # (at - 14 d, at] would touch 15 local dates, the first one cut at 08:00 and today open.
    assert s.method.n == 14 and s.method.coverage == 1.0
    assert [v for _, v in s.series] == [1500 + 20 * (15 - d) for d in range(14, 0, -1)]
    assert s.headline_key == "signals.trend.up"


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
        # an earlier, mistyped entry that day (rising day by day), then the real weigh-in
        put_ref(rig, "body_mass", 30.0 + 1.0 * d, day - timedelta(hours=1), node="manual",
                dev="manual", src="self", crew="crew-a")  # fmt: skip
        put_ref(rig, "body_mass", 80.0 + 0.05 * d, day, node="manual", dev="manual", src="self",
                crew="crew-a")  # fmt: skip
    s = one(rig, "body_mass_30d")
    assert [v for _, v in s.series] == pytest.approx([80.0 + 0.05 * d for d in range(28, 0, -1)])
    assert s.headline_key == "signals.trend.down" and s.value.unit == "kg"
    # Spec section 7: the slope is in kg per week (0.05 kg per day down).
    assert s.value.per == "week" and s.value.estimate == pytest.approx(-0.35, abs=0.01)
    assert s.value.low <= s.value.estimate <= s.value.high


def test_body_mass_counts_30_local_dates(rig):
    for d in range(30, 0, -1):  # 09:00 local, so the first one is inside (at - 30 d, at]
        put_ref(rig, "body_mass", 80.0 + 0.05 * d, END - timedelta(days=d) + timedelta(hours=2),
                node="manual", dev="manual", src="self", crew="crew-a")  # fmt: skip
    put_ref(rig, "body_mass", 79.9, END, node="manual", dev="manual", src="self", crew="crew-a")
    s = one(rig, "body_mass_30d")
    assert s.method.n == 30 and s.method.coverage == 1.0 and len(s.series) == 30


def test_a_crew_less_meal_never_counts_for_a_crew(rig):
    for d in range(13, 0, -1):
        rig.put("intake_water_ml", 1500, END - timedelta(days=d), node="food", dev="catalog",
                src="self", crew=None)  # logged without a crew  # fmt: skip
    s = one(rig, "water_14d")
    assert s.state == "not_enough_data" and s.missing[0].have == 0 and not s.inputs
