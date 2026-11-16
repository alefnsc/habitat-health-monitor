"""Every catalogue signal on the 28-day synthetic replay (D45 §9.2, §10)."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from hub.signals.engine import evaluate
from hub.sim import load_replay
from hub.sim.signals_synth import synth, write
from hub.tests.helpers import Rig, T

TZ = "America/Sao_Paulo"
REPO = Path(__file__).resolve().parents[3]
REAL_RULES = REPO / "data" / "thresholds.json"
END = T.replace(hour=10)  # the last line lands at 07:00 local


@pytest.fixture(scope="module")
def signals(tmp_path_factory):
    from hub.tests.conftest import FakeClock

    clock = FakeClock(END)
    rig = Rig(tmp_path_factory.mktemp("replay"), clock, rule_files=(REAL_RULES,))
    lines = synth()
    last = lines[-1].t_ms
    for i, ln in enumerate(lines, 1):
        msg = {**ln.msg, "node": "sim-1", "boot": 1, "seq": i, "age_ms": last - ln.t_ms,
               "src": "replay"}  # fmt: skip
        assert rig.ing.ingest_reading(msg, channel="test").reason is None
    out = evaluate(rig.store, rig.assessor.rules, crews=["crew-a", "crew-b", "crew-c"],
                   at=END + timedelta(minutes=1), tz=TZ)  # fmt: skip
    return {(s.id, s.crew): s for s in out}


def test_every_replay_signal_is_marked_replay(signals):
    for s in signals.values():
        if s.state != "not_enough_data" or s.inputs:
            assert s.replay and all(i.src == "replay" for i in s.inputs), s.id


def test_crew_b_gets_nothing_from_the_replay(signals):
    assert all(s.state == "not_enough_data" and not s.inputs
               for (i, c), s in signals.items() if c == "crew-b")  # fmt: skip


def test_planted_rest_hr_rise_is_notable_and_flat_crew_is_steady(signals):
    a = signals[("rest_hr_baseline", "crew-a")]
    assert a.state == "notable" and a.headline_key == "signals.baseline.above"
    assert signals[("rest_hr_baseline", "crew-c")].state == "steady"


def test_rh_ramp_reaches_75_in_about_4_hours_not_yet_notable(signals):
    s = signals[("cabin_rh_ttl", None)]
    assert s.headline_key == "signals.ttl.reaches" and s.reference["limit"] == 75
    assert 3.0 <= s.value.low <= s.value.high <= 5.0 and s.state == "steady"
    assert signals[("cabin_rh_6h", None)].headline_key == "signals.trend.up"


def test_steady_and_gapped_series(signals):
    co2 = signals[("cabin_ppco2_ttl", None)]  # flat 1-hour mean far under 3 mmHg
    assert co2.state == "steady" and co2.headline_key in ("signals.ttl.none", "signals.ttl.away")
    assert signals[("spo2_baseline", "crew-c")].state == "not_enough_data"
    assert signals[("sleep_baseline", "crew-a")].state in ("steady", "notable")


def test_food_mass_and_cross_references(signals):
    assert signals[("water_14d", "crew-a")].headline_key == "signals.trend.up"
    assert signals[("water_14d", "crew-c")].state == "not_enough_data"  # every third day only
    assert signals[("body_mass_30d", "crew-a")].headline_key == "signals.trend.down"
    meal = signals[("last_meal_vs_sleep", "crew-a")]
    assert meal.headline_key == "signals.pair.rho" and meal.state == "steady"
    sw = signals[("space_weather_vs_sleep", "crew-a")]
    assert sw.state == "steady" and len(sw.pairs) >= 20
    ce = signals[("cabin_vs_earth", None)]
    assert [x["lag_h"] for x in ce.detail["lags"]] == [0, 1, 2, 3] and ce.value is None


def test_lift_signals_say_not_enough_data_on_the_replay(signals):
    for sid in ("lift_work_sets", "lift_within_set", "lift_tilt_agreement", "training_vs_rest_hr"):
        assert signals[(sid, "crew-a")].state == "not_enough_data", sid


def test_committed_replay_matches_the_generator(tmp_path):
    committed = REPO / "data" / "replay" / "signals-synthetic-28d.jsonl"
    fresh = tmp_path / "fresh.jsonl"
    write(fresh, synth())
    assert committed.read_bytes() == fresh.read_bytes()
    assert json.loads(committed.read_text().splitlines()[0])["kind"] == "note"
    assert len(load_replay(committed)) == len(synth())
