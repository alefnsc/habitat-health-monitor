"""S4: content tests for data/thresholds.json (the reviewed NASA and clinical tables).

Written against docs/drafts/s2-nasa-thresholds.md and s3-clinical-bands.md.
They are skipped until H4b commits data/thresholds.json; from then on they run and
must pass. If the operator changes the S2/S3 tables, these tests follow the tables.
"""

from pathlib import Path

import pytest

from hub.thresholds import load_rules

THRESHOLDS = Path(__file__).resolve().parents[2] / "data" / "thresholds.json"

pytestmark = pytest.mark.skipif(
    not THRESHOLDS.exists(), reason="S4: waiting for H4b to commit data/thresholds.json"
)

EXPECTED_IDS = {
    "co2_1h", "co2_7d", "cabin_health_box_temp", "cabin_health_box_rh",
    "cabin_performance_temp", "cabin_performance_rh", "lux_general",
    "radiation_career", "radiation_spe",
    "hr_rest_low", "hr_rest_high", "spo2_low", "body_temp_low", "body_temp_high",
    "bp_sys_low", "bp_sys_high", "bp_dia_high", "glucose_low", "glucose_high",
    "sleep_night", "sleep_week", "mood_self", "mood_7d",
}  # fmt: skip
VITAL_INDS = {"hr", "spo2", "body_temp", "bp_sys", "bp_dia", "glucose", "sleep_h", "mood"}


@pytest.fixture(scope="module")
def rules():
    return {r.id: r for r in load_rules(THRESHOLDS)}


def test_rule_ids_present(rules):
    assert set(rules) == EXPECTED_IDS
    assert len(rules) == 23


def test_co2_1h_fields(rules):
    r = rules["co2_1h"]
    assert (r.ind, r.window) == ("cabin_ppco2", "mean_1h")
    assert r.ok is not None and r.ok.max == 3.0
    assert r.watch is None
    assert r.act is not None and (r.act.min, r.act.max, r.act.lt, r.act.gt) == (None,) * 4
    assert r.source_kind == "nasa_std"
    assert "[V2 6004]" in r.source_ref
    assert r.url.startswith("https://standards.nasa.gov")


def test_co2_7d_fields(rules):
    r = rules["co2_7d"]
    assert (r.ind, r.window) == ("cabin_ppco2", "mean_7d")
    assert r.ok is not None and r.ok.max == 2.5
    assert r.watch is not None and r.act is None
    assert "TB-004" in r.source_ref  # the 7-day line is not in Vol 2 Rev F (S2 decision 2)


def test_radiation_fields(rules):
    spe = rules["radiation_spe"]
    assert (spe.ind, spe.window) == ("space_weather", "instant")
    assert "[V2 6164]" in spe.source_ref
    career = rules["radiation_career"]
    assert (career.ind, career.window) == ("rad_dose_cum", "instant")
    assert "600 mSv" in career.note and "[V1 4030]" in career.note


def test_mood_7d_fields(rules):
    r = rules["mood_7d"]
    assert (r.ind, r.window) == ("mood", "mean_7d")
    assert r.ok is not None and r.ok.min == 2.5
    assert r.watch is not None and (r.watch.min, r.watch.max, r.watch.lt, r.watch.gt) == (None,) * 4
    assert r.act is None
    assert r.source_kind == "team_convention"
    assert "non-clinical" in r.note.lower() or "not clinical" in r.note.lower()


def test_vitals_never_nasa_std(rules):
    for r in rules.values():
        if r.ind in VITAL_INDS:
            assert r.source_kind != "nasa_std", r.id


def test_source_kind_values(rules):
    for r in rules.values():
        assert r.source_kind in {"nasa_std", "clinical_ref", "team_convention"}, r.id
    assert rules["mood_self"].source_kind == "team_convention"
    assert rules["mood_7d"].source_kind == "team_convention"


def test_every_rule_has_url_and_ref(rules):
    for r in rules.values():
        assert r.url.startswith("https://"), r.id
        assert r.source_ref.strip(), r.id


def test_lux_hours(rules):
    h = rules["lux_general"].hours
    assert h is not None
    assert (h.start.hour, h.start.minute, h.end.hour, h.end.minute) == (7, 0, 23, 0)
