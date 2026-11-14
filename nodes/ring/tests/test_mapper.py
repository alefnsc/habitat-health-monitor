"""Ring mapper: raw pull record -> contract-v1 readings, with no network (D41 §4)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hub.contract import parse_reading
from nodes.ring.mapper import BOOT, CREW, DEV, NODE, map_pull
from nodes.ring.records import append_record, load_records

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data" / "replay" / "ring-synthetic-nights.jsonl"
PULLED = "2026-11-14T12:00:00+00:00"
PULLED_MS = int(datetime(2026, 11, 14, 12, 0, tzinfo=UTC).timestamp() * 1000)


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def hr(iso: str, bpm: int, source: str = "sleep") -> dict:
    return {"timestamp": iso, "timestamp_unix": ms(iso), "bpm": bpm, "source": source}


def night(day: str, end: str, total_s: int | None = 25200, typ: str = "long_sleep") -> dict:
    return {"id": f"s-{day}-{typ}", "day": day, "bedtime_start": "2026-11-13T23:00:00-03:00",
            "bedtime_end": end, "total_sleep_duration": total_s, "type": typ}  # fmt: skip


def record(**parts) -> dict:
    base = {"kind": "ring_pull", "v": 1, "pulled_at": PULLED, "heartrate": [], "daily_spo2": [],
            "sleep": []}  # fmt: skip
    return {**base, **parts}


def inds(res) -> list[str]:
    return [r["ind"] for r in res.readings]


def test_hr_keeps_only_rest_and_sleep_samples():
    rows = [hr("2026-11-14T03:00:00+00:00", 55, "sleep"), hr("2026-11-14T10:00:00+00:00", 62, "rest")]
    rows += [hr("2026-11-14T10:05:00+00:00", 90, s) for s in ("awake", "workout", "live", "session")]
    res = map_pull(record(heartrate=rows), mode="replay")
    assert [(r["ind"], r["val"]) for r in res.readings] == [("hr", 55), ("hr", 62)]
    assert res.skipped == {"hr_source_awake": 1, "hr_source_workout": 1, "hr_source_live": 1,
                           "hr_source_session": 1}  # fmt: skip


def test_sleep_h_from_long_sleep_only():
    end = "2026-11-14T06:40:00-03:00"
    docs = [night("2026-11-14", end, 26100), night("2026-11-14", end, 1800, "late_nap"),
            night("2026-11-14", end, 900, "sleep"), night("2026-11-14", end, None, "deleted"),
            night("2026-11-13", "2026-11-13T07:00:00-03:00", None)]  # fmt: skip
    res = map_pull(record(sleep=docs), mode="replay")
    (r,) = res.readings
    assert (r["ind"], r["val"], r["unit"]) == ("sleep_h", 7.25, "h")
    assert r["age_ms"] == PULLED_MS - ms(end)
    assert res.skipped == {"sleep_type_late_nap": 1, "sleep_type_sleep": 1, "sleep_type_deleted": 1,
                           "sleep_no_duration": 1}  # fmt: skip


def test_spo2_is_timed_at_the_end_of_its_night():
    end = "2026-11-14T06:40:00-03:00"
    spo2 = [{"id": "a", "day": "2026-11-14", "spo2_percentage": {"average": 96.24}},
            {"id": "b", "day": "2026-11-12", "spo2_percentage": {"average": 97.0}},
            {"id": "c", "day": "2026-11-13", "spo2_percentage": None}]  # fmt: skip
    docs = [night("2026-11-14", end), night("2026-11-13", "2026-11-13T07:00:00-03:00")]
    res = map_pull(record(sleep=docs, daily_spo2=spo2), mode="replay")
    (s,) = [r for r in res.readings if r["ind"] == "spo2"]
    assert (s["val"], s["unit"], s["age_ms"]) == (96.2, "%", PULLED_MS - ms(end))
    assert res.skipped == {"spo2_no_night": 1, "spo2_no_value": 1}


def test_skin_temp_is_never_mapped():
    res = map_pull(load_records(FIXTURE)[0], mode="replay")
    assert "skin_temp" not in inds(res)
    assert set(inds(res)) == {"hr", "spo2", "sleep_h"}


def test_envelope_and_every_reading_passes_the_contract():
    for mode, src, boot in (("replay", "replay", 2), ("pull", "hobby", 1)):
        res = map_pull(load_records(FIXTURE)[0], mode=mode, now_ms=PULLED_MS + 60_000)
        assert res.readings
        for r in res.readings:
            p = parse_reading(r)
            assert (p.node, p.dev, p.crew, p.src, p.boot) == (NODE, DEV, CREW, src, boot)
            assert p.q == ("ok",)
    assert (NODE, DEV, CREW, BOOT) == ("ring-1", "RING", "crew-b", {"pull": 1, "replay": 2})


def test_age_is_true_age_on_pull_and_recorded_age_on_replay():
    t = "2026-11-14T05:00:00+00:00"
    rec = record(heartrate=[hr(t, 54)])
    now = PULLED_MS + 3 * 3600_000
    (pulled,) = map_pull(rec, mode="pull", now_ms=now).readings
    (replayed,) = map_pull(rec, mode="replay", now_ms=now).readings
    assert pulled["age_ms"] == now - ms(t)
    assert replayed["age_ms"] == PULLED_MS - ms(t)
    future = record(heartrate=[hr("2026-11-14T13:00:00+00:00", 54)])
    assert map_pull(future, mode="replay").readings[0]["age_ms"] == 0


def test_seq_is_deterministic_per_sample_and_indicator():
    end = "2026-11-14T06:40:00-03:00"
    rec = record(heartrate=[hr("2026-11-14T03:00:00+00:00", 55)], sleep=[night("2026-11-14", end)],
                 daily_spo2=[{"id": "a", "day": "2026-11-14", "spo2_percentage": {"average": 97}}])  # fmt: skip
    a = map_pull(rec, mode="replay").readings
    b = map_pull(rec, mode="replay").readings
    assert a == b
    seqs = {r["ind"]: r["seq"] for r in a}
    end_s = ms(end) // 1000
    assert seqs == {"hr": ms("2026-11-14T03:00:00+00:00") // 1000 * 4 + 1, "spo2": end_s * 4 + 2,
                    "sleep_h": end_s * 4 + 3}  # fmt: skip


def test_out_of_range_values_are_flagged():
    end = "2026-11-14T06:40:00-03:00"
    rec = record(heartrate=[hr("2026-11-14T03:00:00+00:00", 15), hr("2026-11-14T03:05:00+00:00", 251)],
                 sleep=[night("2026-11-14", end, 25 * 3600)],
                 daily_spo2=[{"id": "a", "day": "2026-11-14", "spo2_percentage": {"average": 49}}])  # fmt: skip
    res = map_pull(rec, mode="replay")
    assert {r["ind"]: r["q"] for r in res.readings} == {"hr": ["out_of_range"],
                                                        "spo2": ["out_of_range"],
                                                        "sleep_h": ["out_of_range"]}  # fmt: skip
    for r in res.readings:
        parse_reading(r)


def test_readings_are_ordered_by_measured_time():
    res = map_pull(load_records(FIXTURE)[0], mode="replay")
    keys = [(-r["age_ms"], r["seq"] % 4) for r in res.readings]
    assert keys == sorted(keys)


def test_fixture_counts_and_synthetic_label():
    lines = FIXTURE.read_text().splitlines()
    assert "SYNTHETIC" in lines[0]
    (rec,) = load_records(FIXTURE)
    res = map_pull(rec, mode="replay")
    counts = {i: inds(res).count(i) for i in ("hr", "spo2", "sleep_h")}
    assert counts == {"hr": 94, "spo2": 2, "sleep_h": 2}
    assert res.skipped == {"hr_source_awake": 4, "hr_source_workout": 1, "hr_source_session": 1,
                           "sleep_type_late_nap": 1, "sleep_type_deleted": 1,
                           "spo2_no_night": 1}  # fmt: skip


def test_pull_needs_now_and_mode_is_checked():
    with pytest.raises(ValueError):
        map_pull(record(), mode="pull")
    with pytest.raises(ValueError):
        map_pull(record(), mode="live")  # type: ignore[arg-type]


def test_records_round_trip_with_private_mode(tmp_path):
    path = tmp_path / "ring" / "pulls.jsonl"
    rec = record(heartrate=[hr("2026-11-14T03:00:00+00:00", 55)])
    append_record(path, rec)
    append_record(path, rec)
    assert load_records(path) == [rec, rec]
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_no_vendor_or_company_name_in_the_importer():
    # Both names are spelled backwards so this file does not contain them.
    vendor = re.compile(r"\b" + "aruo"[::-1], re.IGNORECASE)
    company = "diacov"[::-1]
    files = [
        p for p in (ROOT / "nodes" / "ring").rglob("*") if p.is_file() and "__pycache__" not in p.parts
    ]
    files.append(FIXTURE)
    for p in files:
        text = p.read_text(errors="ignore")
        assert not vendor.search(text), p
        assert company not in text.lower(), p
