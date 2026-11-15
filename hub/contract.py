"""Message contract v1: readings and reps (spec 4.1-4.4, D8, D9, NU1)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

INDICATORS: dict[str, str] = {
    "hr": "bpm",
    "spo2": "%",
    "skin_temp": "C",
    "body_temp": "C",
    "bp_sys": "mmHg",
    "bp_dia": "mmHg",
    "glucose": "mg/dL",
    "sleep_h": "h",
    "mood": "1-5",
    "symptom": "code",
    "cabin_temp": "C",
    "cabin_rh": "%",
    "cabin_p": "hPa",
    "cabin_co2": "ppm",
    "cabin_lux": "lx",
    "motion": "g",
    "load_raw": "N",
    "tilt": "state",
    "space_weather": "level",
    "rad_dose_cum": "mSv",
    "intake_kcal": "kcal",
    "intake_protein_g": "g",
    "intake_carb_g": "g",
    "intake_fat_g": "g",
    "intake_water_ml": "mL",
    "intake_sodium_mg": "mg",
    "intake_potassium_mg": "mg",
    "intake_calcium_mg": "mg",
    "intake_iron_mg": "mg",
    "intake_vitd_ug": "ug",
    "body_mass": "kg",
    # Reference feeds (D45 §4.2): stored for signals, never assessed, outboxed or on /api/status.
    "iss_cabin_p": "hPa",
    "iss_cabin_temp": "C",
    "iss_ppco2": "mmHg",  # the US Lab item
    "iss_ppco2_node3": "mmHg",  # Node 3: another module, never pooled with the Lab
    "earth_temp": "C",
    "earth_rh": "%",
    "earth_p": "hPa",
}
REFERENCE_INDS: frozenset[str] = frozenset(
    {"iss_cabin_p", "iss_cabin_temp", "iss_ppco2", "iss_ppco2_node3", "earth_temp", "earth_rh",
     "earth_p"}
)
DERIVED: dict[str, str] = {"cabin_ppco2": "mmHg"}

CABIN_INDS: frozenset[str] = frozenset(
    {"cabin_temp", "cabin_rh", "cabin_p", "cabin_co2", "cabin_ppco2", "cabin_lux"}
)
BODY_INDS: frozenset[str] = frozenset(
    {
        "hr", "spo2", "skin_temp", "body_temp", "bp_sys", "bp_dia",
        "glucose", "sleep_h", "mood", "symptom", "body_mass",
    }
)  # fmt: skip
INTAKE_ORDER: tuple[str, ...] = (
    "intake_kcal",
    "intake_protein_g",
    "intake_carb_g",
    "intake_fat_g",
    "intake_water_ml",
    "intake_sodium_mg",
    "intake_potassium_mg",
    "intake_calcium_mg",
    "intake_iron_mg",
    "intake_vitd_ug",
)
INTAKE_INDS: frozenset[str] = frozenset(INTAKE_ORDER)
INTAKE_UNITS: dict[str, str] = {i: INDICATORS[i] for i in INTAKE_ORDER}
INTAKE_CEILINGS: dict[str, float] = {
    "intake_kcal": 10000,
    "intake_protein_g": 500,
    "intake_carb_g": 1000,
    "intake_fat_g": 500,
    "intake_water_ml": 10000,
    "intake_sodium_mg": 30000,
    "intake_potassium_mg": 30000,
    "intake_calcium_mg": 20000,
    "intake_iron_mg": 1000,
    "intake_vitd_ug": 5000,
}
BODY_MASS_RANGE: tuple[float, float] = (20.0, 300.0)

NODES: frozenset[str] = frozenset(
    {"vitals-1", "cabin-1", "exercise-1", "strap-1", "manual", "camera", "sim-1", "nasa", "food",
     "tilt-1", "ring-1", "earth-1"}
)
SOURCES: frozenset[str] = frozenset({"certified", "hobby", "self", "nasa", "replay", "ref"})
DEVICES: frozenset[str] = frozenset(
    {
        "MAX30102", "DS18B20", "MLX90614", "SCD41", "BME280", "DHT22", "DHT11", "BH1750",
        "HX711", "H10", "manual", "camera", "MPU6050", "MH-Z19", "DONKI", "OSDR", "catalog",
        "NTC", "KY039", "KY017", "RING", "ISSLIVE", "WEATHER",
    }
)  # fmt: skip
FLAGS: frozenset[str] = frozenset(
    {"ok", "motion", "no_contact", "settling", "leads_off", "out_of_range",
     "assumed_pressure", "stale"}
)  # fmt: skip
CREWS: frozenset[str] = frozenset({"crew-a", "crew-b", "crew-c"})
SYMPTOM_CODES: frozenset[str] = frozenset({"headache", "fatigue", "nausea", "poor_sleep", "none"})
REP_SOURCES: frozenset[str] = frozenset({"camera", "load_cell"})
# Exercises the astronaut picks on the camera page: wrist-tracked vertical lifts only.
EXERCISES: frozenset[str] = frozenset({"curl", "overhead_press", "row"})

REASON_CODES: tuple[str, ...] = (
    "bad_json",
    "too_large",
    "bad_version",
    "missing_field:",
    "bad_type:",
    "bad_value:",
    "unknown_node",
    "unknown_ind",
    "derived_ind",
    "unit_mismatch",
    "unknown_src",
    "unknown_dev",
    "unknown_flag",
    "bad_flags",
    "bad_crew",
)


class ContractError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Reading:
    v: int
    node: str
    boot: int
    seq: int
    age_ms: int
    ind: str
    val: float
    unit: str
    src: str
    dev: str
    q: tuple[str, ...]
    crew: str | None
    code: str | None


@dataclass(frozen=True)
class Rep:
    v: int
    node: str
    boot: int
    seq: int
    age_ms: int
    type: str
    session: str
    rep: int
    src: str
    peak_n: float
    work_j: float | None
    rom_m: float | None
    g: float
    mass_kg: float
    t0_ms: int
    t1_ms: int
    work_ecc_j: float | None = None
    t_con_ms: int | None = None
    t_ecc_ms: int | None = None
    t_turn_ms: int | None = None
    exercise: str | None = None


_READING_FIELDS = (
    ("v", "int"), ("node", "str"), ("boot", "int"), ("seq", "int"), ("age_ms", "int"),
    ("ind", "str"), ("val", "num"), ("unit", "str"), ("src", "str"), ("dev", "str"),
    ("q", "list"),
)  # fmt: skip
_REP_FIELDS = (
    ("v", "int"), ("node", "str"), ("boot", "int"), ("seq", "int"), ("age_ms", "int"),
    ("type", "str"), ("session", "str"), ("rep", "int"), ("src", "str"),
    ("peak_n", "num"), ("work_j", "num?"), ("rom_m", "num?"), ("g", "num"),
    ("mass_kg", "num"), ("t0_ms", "int"), ("t1_ms", "int"),
)  # fmt: skip


def _decode(raw: bytes | str | dict, max_bytes: int | None) -> dict:
    if isinstance(raw, dict):
        return raw
    data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    if max_bytes is not None and len(data) > max_bytes:
        raise ContractError("too_large")
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ContractError("bad_json") from None
    if not isinstance(obj, dict):
        raise ContractError("bad_json")
    return obj


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_fields(msg: dict, fields: tuple[tuple[str, str], ...]) -> None:
    v = msg.get("v", None)
    if "v" not in msg or not _is_int(v) or v != 1:
        raise ContractError("bad_version")
    for name, _kind in fields:
        if name not in msg:
            raise ContractError(f"missing_field:{name}")
    for name, kind in fields:
        x = msg[name]
        if kind == "int":
            ok = _is_int(x)
        elif kind == "str":
            ok = isinstance(x, str)
        elif kind == "num":
            ok = _is_num(x)
        elif kind == "num?":
            ok = x is None or _is_num(x)
        else:
            ok = isinstance(x, list)
        if not ok:
            raise ContractError(f"bad_type:{name}")


def _finite(x: float) -> bool:
    return math.isfinite(x)


def parse_reading(raw: bytes | str | dict, *, max_bytes: int | None = None) -> Reading:
    msg = _decode(raw, max_bytes)
    _check_fields(msg, _READING_FIELDS)
    ind = msg["ind"]
    if ind == "symptom" and msg.get("code") is None:
        raise ContractError("missing_field:code")
    if "code" in msg and msg["code"] is not None and not isinstance(msg["code"], str):
        raise ContractError("bad_type:code")
    crew = msg.get("crew")
    if crew is not None and not isinstance(crew, str):
        raise ContractError("bad_type:crew")
    q = msg["q"]
    if any(not isinstance(f, str) for f in q):
        raise ContractError("bad_type:q")
    # enums
    if msg["node"] not in NODES:
        raise ContractError("unknown_node")
    if ind in DERIVED:
        raise ContractError("derived_ind")
    if ind not in INDICATORS:
        raise ContractError("unknown_ind")
    if msg["src"] not in SOURCES:
        raise ContractError("unknown_src")
    if msg["dev"] not in DEVICES:
        raise ContractError("unknown_dev")
    if not q:
        raise ContractError("bad_flags")
    if any(f not in FLAGS for f in q):
        raise ContractError("unknown_flag")
    if crew is not None and crew not in CREWS:
        raise ContractError("bad_crew")
    if msg["unit"] != INDICATORS[ind]:
        raise ContractError("unit_mismatch")
    # values
    val = float(msg["val"])
    if not _finite(val):
        raise ContractError("bad_value:val")
    if msg["seq"] < 1:
        raise ContractError("bad_value:seq")
    if msg["boot"] < 0:
        raise ContractError("bad_value:boot")
    if msg["age_ms"] < 0:
        raise ContractError("bad_value:age_ms")
    code: str | None = None
    if ind == "symptom":
        code = msg["code"]
        if code not in SYMPTOM_CODES:
            raise ContractError("bad_value:code")
    if ind in INTAKE_CEILINGS and not 0 <= val <= INTAKE_CEILINGS[ind]:
        raise ContractError("bad_value:val")
    if ind == "body_mass" and not BODY_MASS_RANGE[0] <= val <= BODY_MASS_RANGE[1]:
        raise ContractError("bad_value:val")
    return Reading(
        v=1,
        node=msg["node"],
        boot=msg["boot"],
        seq=msg["seq"],
        age_ms=msg["age_ms"],
        ind=ind,
        val=val,
        unit=msg["unit"],
        src=msg["src"],
        dev=msg["dev"],
        q=tuple(q),
        crew=crew,
        code=code,
    )


def parse_rep(raw: bytes | str | dict, *, max_bytes: int | None = None) -> Rep:
    msg = _decode(raw, max_bytes)
    _check_fields(msg, _REP_FIELDS)
    if msg["type"] != "rep":
        raise ContractError("bad_value:type")
    if msg["node"] not in NODES:
        raise ContractError("unknown_node")
    if msg["src"] not in REP_SOURCES:
        raise ContractError("bad_value:src")
    if msg["work_j"] is None and msg["src"] != "load_cell":
        raise ContractError("bad_type:work_j")
    if msg["seq"] < 1:
        raise ContractError("bad_value:seq")
    if msg["boot"] < 0:
        raise ContractError("bad_value:boot")
    if msg["age_ms"] < 0:
        raise ContractError("bad_value:age_ms")
    if msg["rep"] < 1:
        raise ContractError("bad_value:rep")
    session = msg["session"]
    if not session or len(session) > 64:
        raise ContractError("bad_value:session")
    for name in ("peak_n", "work_j", "rom_m", "g", "mass_kg"):
        x = msg[name]
        if x is not None and not _finite(float(x)):
            raise ContractError(f"bad_value:{name}")
    if msg["mass_kg"] <= 0:
        raise ContractError("bad_value:mass_kg")
    if msg["g"] < 0:
        raise ContractError("bad_value:g")
    if msg["t0_ms"] < 0:
        raise ContractError("bad_value:t0_ms")
    if msg["t1_ms"] < msg["t0_ms"]:
        raise ContractError("bad_value:t1_ms")

    ecc = msg.get("work_ecc_j")
    if ecc is not None:
        if not _is_num(ecc):
            raise ContractError("bad_type:work_ecc_j")
        if not _finite(float(ecc)) or ecc < 0:
            raise ContractError("bad_value:work_ecc_j")
    for name in ("t_con_ms", "t_ecc_ms", "t_turn_ms"):
        x = msg.get(name)
        if x is None:
            continue
        if not _is_int(x):
            raise ContractError(f"bad_type:{name}")
        if x < 0:
            raise ContractError(f"bad_value:{name}")
    turn = msg.get("t_turn_ms")
    if turn is not None and not (msg["t0_ms"] <= turn <= msg["t1_ms"]):
        raise ContractError("bad_value:t_turn_ms")
    exercise = msg.get("exercise")
    if exercise is not None:
        if not isinstance(exercise, str):
            raise ContractError("bad_type:exercise")
        if exercise not in EXERCISES:
            raise ContractError("bad_value:exercise")

    def opt(x: Any) -> float | None:
        return None if x is None else float(x)

    return Rep(
        v=1,
        node=msg["node"],
        boot=msg["boot"],
        seq=msg["seq"],
        age_ms=msg["age_ms"],
        type="rep",
        session=session,
        rep=msg["rep"],
        src=msg["src"],
        peak_n=float(msg["peak_n"]),
        work_j=opt(msg["work_j"]),
        rom_m=opt(msg["rom_m"]),
        g=float(msg["g"]),
        mass_kg=float(msg["mass_kg"]),
        t0_ms=msg["t0_ms"],
        t1_ms=msg["t1_ms"],
        work_ecc_j=opt(ecc),
        t_con_ms=msg.get("t_con_ms"),
        t_ecc_ms=msg.get("t_ecc_ms"),
        t_turn_ms=turn,
        exercise=exercise,
    )


def validate_reading(msg: dict) -> list[str]:
    try:
        parse_reading(msg)
    except ContractError as e:
        return [e.reason]
    return []


def validate_rep(msg: dict) -> list[str]:
    try:
        parse_rep(msg)
    except ContractError as e:
        return [e.reason]
    return []


def is_assessable(r: Reading) -> bool:
    return r.q == ("ok",)


def reading_to_dict(r: Reading) -> dict:
    return {
        "v": r.v, "node": r.node, "boot": r.boot, "seq": r.seq, "age_ms": r.age_ms,
        "ind": r.ind, "val": r.val, "unit": r.unit, "src": r.src, "dev": r.dev,
        "q": list(r.q), "crew": r.crew, "code": r.code,
    }  # fmt: skip


def rep_to_dict(r: Rep) -> dict:
    return {
        "v": r.v, "node": r.node, "boot": r.boot, "seq": r.seq, "age_ms": r.age_ms,
        "type": r.type, "session": r.session, "rep": r.rep, "src": r.src,
        "peak_n": r.peak_n, "work_j": r.work_j, "rom_m": r.rom_m, "g": r.g,
        "mass_kg": r.mass_kg, "t0_ms": r.t0_ms, "t1_ms": r.t1_ms,
        "work_ecc_j": r.work_ecc_j, "t_con_ms": r.t_con_ms, "t_ecc_ms": r.t_ecc_ms,
        "t_turn_ms": r.t_turn_ms, "exercise": r.exercise,
    }  # fmt: skip
