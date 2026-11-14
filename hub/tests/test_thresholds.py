import json
import logging
from datetime import time
from pathlib import Path

import pytest

from hub.thresholds import (
    WINDOWS,
    Hours,
    ThresholdsError,
    band_status,
    load_rule_files,
    load_rules,
    parse_rules,
    rules_for,
)

FIX = Path(__file__).parent / "fixtures"
MAIN = FIX / "thresholds_test.json"
FOOD = FIX / "thresholds_food_test.json"


def base(**kw):
    d = {
        "id": "x", "ind": "hr", "window": "instant", "ok": {"max": 3},
        "source_kind": "team_convention", "source_ref": "t",
    }  # fmt: skip
    d.update(kw)
    return d


def by_id(rules, rid):
    return next(r for r in rules if r.id == rid)


def test_load_fixture():
    rules = load_rules(MAIN)
    assert len(rules) == 8 and [r.order for r in rules] == list(range(8))
    assert [r.id for r in rules_for(rules, "cabin_temp")] == [
        "cabin_performance_temp", "cabin_health_box_temp", "t_temp_1h",
    ]  # fmt: skip


def test_band_order_ok_watch_act():
    r = by_id(load_rules(MAIN), "t_hr")
    got = [band_status(r, x) for x in (100, 100.5, 120, 121, 39, 50)]
    assert got == ["ok", "watch", "watch", "act", "act", "ok"]


def test_empty_band_matches_all():
    r = by_id(load_rules(MAIN), "co2_1h")
    assert band_status(r, 3.0) == "ok" and band_status(r, 3.0001) == "act"


def test_exclusive_keys():
    r = by_id(load_rules(MAIN), "t_sleep_cum")
    assert [band_status(r, x) for x in (9.99, 10, 19.99, 20)] == ["ok", "watch", "watch", "act"]


def test_absent_band_never_matches():
    (r,) = parse_rules([base()])
    assert band_status(r, 4) == "unknown"


def test_hours():
    h = by_id(load_rules(MAIN), "t_lux_awake").hours
    assert [h.contains(time(*t)) for t in ((6, 59), (7, 0), (22, 59), (23, 0))] == [
        False, True, True, False,
    ]  # fmt: skip
    n = Hours(time(23, 0), time(7, 0))
    assert n.contains(time(0, 0)) and not n.contains(time(12, 0))


def test_reject_unknown_window():
    with pytest.raises(ThresholdsError) as e:
        parse_rules([base(id="w", window="mean_2h")])
    assert "w" in str(e.value) and "window" in str(e.value)


def test_window_sum_24h_floor():
    rules = load_rules(FOOD)
    assert len(rules) == 2 and "sum_24h_floor" in WINDOWS
    fl = by_id(rules, "t_na_floor")
    got = [band_status(fl, x) for x in (1500, 1499.9, 500, 499.9)]
    assert got == ["ok", "watch", "watch", "act"]
    with pytest.raises(ThresholdsError, match="window"):
        parse_rules([base(window="sum_24h")])


def test_load_rule_files_order(caplog, tmp_path):
    rules = load_rule_files([MAIN, FOOD])
    assert len(rules) == 10 and [r.order for r in rules] == list(range(10))
    assert [r.id for r in rules[-2:]] == ["t_na_max", "t_na_floor"]
    assert [r.id for r in rules_for(rules, "intake_sodium_mg")] == ["t_na_max", "t_na_floor"]
    gone = tmp_path / "nope.json"
    with caplog.at_level(logging.WARNING):
        assert len(load_rule_files([MAIN, gone])) == 8
    assert str(gone) in caplog.text
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps([json.loads(MAIN.read_text())[0]]))
    with pytest.raises(ThresholdsError):
        load_rule_files([MAIN, dup])


def test_reject_bad_band():
    with pytest.raises(ThresholdsError, match="min > max"):
        parse_rules([base(ok={"min": 5, "max": 1})])
    with pytest.raises(ThresholdsError, match="maxx"):
        parse_rules([base(ok={"maxx": 3})])


def test_reject_bad_hours():
    with pytest.raises(ThresholdsError, match="hours"):
        parse_rules([base(hours={"start": "25:00", "end": "07:00"})])
    with pytest.raises(ThresholdsError, match="hours"):
        parse_rules([base(hours={"end": "07:00"})])


def test_source_kinds():
    assert parse_rules([base(source_kind="team_convention")])
    with pytest.raises(ThresholdsError):
        parse_rules([base(source_kind="nasa")])
    d = base()
    del d["source_kind"]
    with pytest.raises(ThresholdsError, match="source_kind"):
        parse_rules([d])


def test_reject_duplicate():
    with pytest.raises(ThresholdsError):
        parse_rules([base(), base()])


def test_same_id_two_inds_allowed():
    assert (
        len(parse_rules([base(id="x_box", ind="cabin_temp"), base(id="x_box", ind="cabin_rh")]))
        == 2
    )


def test_unknown_ind_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_rules([base(ind="rad_dose_msv")])
    assert "rad_dose_msv" in caplog.text


def test_missing_file(caplog, tmp_path):
    p = tmp_path / "none.json"
    with caplog.at_level(logging.WARNING):
        assert load_rules(p) == []
    assert str(p) in caplog.text


def test_repo_file_loads():
    p = Path(__file__).resolve().parents[2] / "data" / "thresholds.json"
    if not p.exists():
        pytest.skip("thresholds not committed yet")
    assert load_rules(p)
