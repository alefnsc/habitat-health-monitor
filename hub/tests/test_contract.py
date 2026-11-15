import json

import pytest

from hub.assess import UNGATED_INDS
from hub.contract import (
    BODY_INDS,
    CABIN_INDS,
    INTAKE_INDS,
    INTAKE_ORDER,
    REASON_CODES,
    ContractError,
    is_assessable,
    parse_reading,
    parse_rep,
    reading_to_dict,
    rep_to_dict,
    validate_reading,
    validate_rep,
)

BASE = {
    "v": 1, "node": "cabin-1", "boot": 2, "seq": 10, "age_ms": 0, "ind": "cabin_co2",
    "val": 812, "unit": "ppm", "src": "hobby", "dev": "SCD41", "q": ["ok"],
}  # fmt: skip
INTAKE = {
    "v": 1, "node": "food", "boot": 1763121600, "seq": 1, "age_ms": 0,
    "ind": "intake_sodium_mg", "val": 210, "unit": "mg", "src": "self", "dev": "catalog",
    "q": ["ok"], "crew": "crew-a",
}  # fmt: skip
REP = {
    "v": 1, "node": "camera", "boot": 1763121600, "seq": 1, "age_ms": 0, "type": "rep",
    "session": "s1", "rep": 1, "src": "camera", "peak_n": 123.4, "work_j": 45.6,
    "rom_m": 0.42, "g": 9.81, "mass_kg": 10, "t0_ms": 1200, "t1_ms": 3100,
}  # fmt: skip

CASES: list[tuple[str, dict, str]] = []  # (label, message, reason); filled below
SEEN: set[str] = set()


def reason_of(msg, rep=False) -> str:
    fn = parse_rep if rep else parse_reading
    with pytest.raises(ContractError) as e:
        fn(msg)
    SEEN.add(e.value.reason)
    return e.value.reason


def mod(base, **kw):
    d = dict(base)
    for k, v in kw.items():
        if v is KeyError:
            d.pop(k, None)
        else:
            d[k] = v
    return d


def test_valid_mcu_reading():
    r = parse_reading(json.dumps(BASE).encode(), max_bytes=256)
    assert r.val == 812.0 and isinstance(r.val, float)
    assert r.q == ("ok",) and r.crew is None and r.code is None


def test_too_large():
    raw = json.dumps({**BASE, "pad": "x" * 200}).encode()
    assert reason_of_raw(raw, 256) == "too_large"
    assert parse_reading(raw).val == 812.0


def reason_of_raw(raw, max_bytes=None, rep=False):
    fn = parse_rep if rep else parse_reading
    with pytest.raises(ContractError) as e:
        fn(raw, max_bytes=max_bytes)
    SEEN.add(e.value.reason)
    return e.value.reason


def test_bad_json():
    for raw in (b'{"v":1,', b"\xff\xfe", b"[]"):
        assert reason_of_raw(raw) == "bad_json"


def test_version():
    for v in (2, True, "1"):
        assert reason_of(mod(BASE, v=v)) == "bad_version"


def test_missing_field_order():
    assert reason_of(mod(BASE, age_ms=KeyError, unit="BPM", ind="hr")) == "missing_field:age_ms"


def test_bool_is_not_number():
    assert reason_of(mod(BASE, seq=True)) == "bad_type:seq"
    assert reason_of(mod(BASE, val=True)) == "bad_type:val"
    assert reason_of(mod(BASE, val="812")) == "bad_type:val"


def test_non_finite():
    for tok in ("NaN", "Infinity"):
        raw = json.dumps(BASE).replace("812", tok)
        assert reason_of_raw(raw) == "bad_value:val"


def test_ranges():
    assert reason_of(mod(BASE, seq=0)) == "bad_value:seq"
    assert reason_of(mod(BASE, boot=-1)) == "bad_value:boot"
    assert reason_of(mod(BASE, age_ms=-5)) == "bad_value:age_ms"


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"node": "vitals-9"}, "unknown_node"),
        ({"ind": "heart"}, "unknown_ind"),
        ({"ind": "hr", "unit": "BPM"}, "unit_mismatch"),
        ({"src": "lab"}, "unknown_src"),
        ({"dev": "MAX30100"}, "unknown_dev"),
        ({"q": ["wet"]}, "unknown_flag"),
        ({"q": []}, "bad_flags"),
        ({"q": "ok"}, "bad_type:q"),
        ({"ind": "cabin_ppco2", "unit": "mmHg"}, "derived_ind"),
        ({"crew": "crew-z"}, "bad_crew"),
    ],
)
def test_enums(kw, reason):
    assert reason_of(mod(BASE, **kw)) == reason


def test_crew():
    assert parse_reading(mod(BASE, crew=None)).crew is None
    assert parse_reading(mod(BASE, crew="crew-b")).crew == "crew-b"


def test_symptom_code():
    s = {
        "v": 1, "node": "manual", "boot": 1763121600, "seq": 1, "age_ms": 0, "ind": "symptom",
        "val": 1, "unit": "code", "src": "self", "dev": "manual", "q": ["ok"],
    }  # fmt: skip
    assert parse_reading({**s, "code": "headache"}).code == "headache"
    assert reason_of(s) == "missing_field:code"
    assert reason_of({**s, "code": "dizzy"}) == "bad_value:code"
    hr = mod(BASE, ind="hr", unit="bpm", code="headache")
    assert parse_reading(hr).code is None


def test_mpu6050_device():
    m = mod(BASE, node="vitals-1", ind="motion", unit="g", dev="MPU6050")
    assert parse_reading(m).dev == "MPU6050"


def test_nasa_readings():
    n = {
        "v": 1, "node": "nasa", "boot": 0, "seq": 1763121600000, "age_ms": 0,
        "ind": "space_weather", "val": 2, "unit": "level", "src": "nasa", "dev": "DONKI",
        "q": ["ok"],
    }  # fmt: skip
    assert parse_reading(n).val == 2.0
    d = {**n, "ind": "rad_dose_cum", "val": 312.5, "unit": "mSv", "dev": "OSDR"}
    assert parse_reading(d).val == 312.5
    assert reason_of({**n, "unit": "mSv"}) == "unit_mismatch"


def test_valid_intake():
    r = parse_reading(INTAKE)
    assert r.val == 210.0 and r.node == "food"


def test_units_intake():
    units = {
        "intake_kcal": "kcal", "intake_protein_g": "g", "intake_carb_g": "g",
        "intake_fat_g": "g", "intake_water_ml": "mL", "intake_sodium_mg": "mg",
        "intake_potassium_mg": "mg", "intake_calcium_mg": "mg", "intake_iron_mg": "mg",
        "intake_vitd_ug": "ug",
    }  # fmt: skip
    for ind, unit in units.items():
        assert parse_reading(mod(INTAKE, ind=ind, unit=unit)).unit == unit
    assert reason_of(mod(INTAKE, ind="intake_vitd_ug", unit="µg")) == "unit_mismatch"
    assert reason_of(mod(INTAKE, ind="intake_water_ml", unit="ml")) == "unit_mismatch"


def test_negative_and_ceiling():
    assert reason_of(mod(INTAKE, val=-1)) == "bad_value:val"
    k = mod(INTAKE, ind="intake_kcal", unit="kcal")
    assert parse_reading(mod(k, val=10000)).val == 10000
    assert reason_of(mod(k, val=10000.1)) == "bad_value:val"
    assert parse_reading(mod(INTAKE, val=30000)).val == 30000
    assert reason_of(mod(INTAKE, val=30000.1)) == "bad_value:val"
    assert parse_reading(mod(INTAKE, ind="intake_vitd_ug", unit="ug", val=0)).val == 0


def test_body_mass():
    b = {
        "v": 1, "node": "manual", "boot": 1763121600, "seq": 1, "age_ms": 0, "ind": "body_mass",
        "val": 70, "unit": "kg", "src": "self", "dev": "manual", "q": ["ok"],
    }  # fmt: skip
    assert parse_reading(b).val == 70 and "body_mass" in BODY_INDS
    assert reason_of({**b, "val": 19.9}) == "bad_value:val"
    assert reason_of({**b, "val": 300.1}) == "bad_value:val"
    assert parse_reading({**b, "val": 20}).val == 20
    assert parse_reading({**b, "val": 300}).val == 300


def test_intake_not_body():
    assert not (INTAKE_INDS & BODY_INDS)
    assert len(INTAKE_INDS) == 10
    assert INTAKE_ORDER[0] == "intake_kcal" and INTAKE_ORDER[-1] == "intake_vitd_ug"
    assert set(INTAKE_ORDER) == INTAKE_INDS


def test_catalog_dev():
    m = mod(INTAKE, node="sim-1", src="replay", ind="intake_kcal", unit="kcal")
    assert parse_reading(m).dev == "catalog"


def test_w_agent_devices():
    ntc = mod(BASE, ind="skin_temp", unit="C", dev="NTC", node="vitals-1")
    ky = mod(BASE, ind="hr", unit="bpm", dev="KY039", node="vitals-1")
    assert parse_reading(ntc).dev == "NTC" and parse_reading(ky).dev == "KY039"


def test_extra_fields_dropped():
    r = parse_reading(mod(BASE, foo=1))
    assert "foo" not in reading_to_dict(r)


def test_valid_camera_rep():
    r = parse_rep(REP)
    assert (r.session, r.rep, r.peak_n, r.work_j, r.rom_m, r.g) == (
        "s1",
        1,
        123.4,
        45.6,
        0.42,
        9.81,
    )
    assert (r.mass_kg, r.t0_ms, r.t1_ms) == (10.0, 1200, 3100)


def test_invalid_reps():
    assert parse_rep(mod(REP, rom_m=None)).rom_m is None
    cases = [
        (mod(REP, type="set"), "bad_value:type"),
        (mod(REP, src="replay"), "bad_value:src"),
        (mod(REP, rep=0), "bad_value:rep"),
        (mod(REP, t1_ms=1000), "bad_value:t1_ms"),
        (mod(REP, mass_kg=0), "bad_value:mass_kg"),
        (mod(REP, g=-1), "bad_value:g"),
        (mod(REP, session=""), "bad_value:session"),
        (mod(REP, work_j=None), "bad_type:work_j"),
    ]
    for msg, reason in cases:
        assert reason_of(msg, rep=True) == reason
    assert parse_rep(mod(REP, src="load_cell", work_j=None, rom_m=None)).work_j is None


def test_validate_helpers():
    assert validate_reading(BASE) == []
    assert validate_reading(mod(BASE, ind="hr", unit="BPM")) == ["unit_mismatch"]
    assert validate_rep(REP) == []
    assert validate_rep(mod(REP, rep=0)) == ["bad_value:rep"]


def test_is_assessable():
    assert is_assessable(parse_reading(BASE))
    assert not is_assessable(parse_reading(mod(BASE, q=["ok", "motion"])))
    assert not is_assessable(parse_reading(mod(BASE, q=["settling"])))


def test_zz_every_reason_code_hit():
    # Runs last in the module: SEEN was filled by the cases above.
    for code in REASON_CODES:
        if code.endswith(":"):
            assert any(r.startswith(code) for r in SEEN), code
        else:
            assert code in SEEN, code


def test_tilt_node_dev_ind():
    t = {"node": "tilt-1", "ind": "tilt", "val": 1, "unit": "state", "dev": "KY017"}
    r = parse_reading(mod(BASE, **t))
    assert (r.node, r.ind, r.val, r.unit, r.dev) == ("tilt-1", "tilt", 1.0, "state", "KY017")
    assert reason_of(mod(BASE, **{**t, "unit": "bool"})) == "unit_mismatch"
    assert "tilt" not in BODY_INDS and "tilt" not in CABIN_INDS
    assert "tilt" in UNGATED_INDS


def test_ring_node_and_device():
    """D41: the wearable ring importer posts as ring-1 with the generic RING device code."""
    from pathlib import Path

    t = {"node": "ring-1", "ind": "hr", "val": 58, "unit": "bpm", "dev": "RING",
         "age_ms": 3_600_000, "crew": "crew-b"}  # fmt: skip
    r = parse_reading(mod(BASE, **t))
    assert (r.node, r.dev, r.age_ms, r.crew) == ("ring-1", "RING", 3_600_000, "crew-b")
    root = Path(__file__).resolve().parents[2]
    fw = root / "firmware/libraries/HabitatNode/src"
    assert "DEV_RING, DEV_BMP280, DEV_COUNT" in (fw / "ReadingFormat.h").read_text()
    assert '"KY017", "RING", "BMP280"}' in (fw / "ReadingFormat.cpp").read_text()
    assert '"dev.RING": "Ring (delayed cloud sync)"' in (root / "console/src/copy.ts").read_text()


def test_rep_phase_fields():
    r = parse_rep(mod(REP, work_ecc_j=20.5, t_con_ms=900, t_ecc_ms=1000, t_turn_ms=2100))
    assert (r.work_ecc_j, r.t_con_ms, r.t_ecc_ms, r.t_turn_ms) == (20.5, 900, 1000, 2100)
    d = rep_to_dict(r)
    assert (d["work_ecc_j"], d["t_con_ms"], d["t_ecc_ms"], d["t_turn_ms"]) == (20.5, 900, 1000, 2100)
    old = parse_rep(REP)
    assert (old.work_ecc_j, old.t_con_ms, old.t_ecc_ms, old.t_turn_ms) == (None, None, None, None)
    assert parse_rep(mod(REP, work_ecc_j=None, t_turn_ms=None)).t_turn_ms is None
    cases = [
        (mod(REP, work_ecc_j="x"), "bad_type:work_ecc_j"),
        (mod(REP, work_ecc_j=-1), "bad_value:work_ecc_j"),
        (mod(REP, t_con_ms=1.5), "bad_type:t_con_ms"),
        (mod(REP, t_ecc_ms=-1), "bad_value:t_ecc_ms"),
        (mod(REP, t_turn_ms=5000), "bad_value:t_turn_ms"),
        (mod(REP, t_turn_ms=1000), "bad_value:t_turn_ms"),
    ]
    for m, reason in cases:
        assert reason_of(m, rep=True) == reason


def test_rep_exercise_field():
    # Older reps carry no exercise and still validate.
    assert parse_rep(REP).exercise is None
    assert parse_rep(mod(REP, exercise=None)).exercise is None
    assert rep_to_dict(parse_rep(REP))["exercise"] is None
    for ex in ("curl", "overhead_press", "row"):
        r = parse_rep(mod(REP, exercise=ex))
        assert r.exercise == ex and rep_to_dict(r)["exercise"] == ex
    assert validate_rep(mod(REP, exercise="squat")) == ["bad_value:exercise"]
    assert validate_rep(mod(REP, exercise="")) == ["bad_value:exercise"]
    assert validate_rep(mod(REP, exercise=1)) == ["bad_type:exercise"]
