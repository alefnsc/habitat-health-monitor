"""N6 Part B: OSDR EDA snapshot fetcher."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from hub.nasa import osdr
from hub.nasa.osdr import SeriesSummary, summarise_series, to_absorbed_mgy

FIX = Path(__file__).parent / "fixtures"
BASE = osdr.EDA_BASE
NOW = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def _fx(rel: str) -> object:
    return json.loads((FIX / rel).read_text())


def test_summary_basic():
    s = summarise_series([21.0, 22.0, 23.5])
    assert s == SeriesSummary(n=3, mean=22.17, min=21.0, max=23.5)


def test_summary_skips_non_numeric():
    s = summarise_series(["21.0", "", "NaN", None])
    assert s is not None and s.n == 1 and s.mean == 21.0


def test_summary_empty_is_none():
    assert summarise_series([]) is None


def test_absorbed_from_microgray():
    assert to_absorbed_mgy(2500, "uGy") == 2.5


def test_absorbed_from_milligray():
    assert to_absorbed_mgy(2.5, "mGy") == 2.5


def test_absorbed_unknown_unit_is_none():
    assert to_absorbed_mgy(2.5, "") is None


def test_co2_unit_mmhg_kept():
    cabin = osdr.summarise_cabin([21.0], [40.0], [2.0, 3.0], co2_unit="mmHg")
    assert cabin["co2_mmhg"]["n"] == 2 and cabin["co2_mmhg"]["mean"] == 2.5
    assert "co2_raw" not in cabin


def test_co2_other_unit_kept_raw():
    cabin = osdr.summarise_cabin([21.0], [40.0], [2600, 3900], co2_unit="ppm")
    assert cabin["co2_mmhg"] is None
    assert cabin["co2_raw"]["mean"] == 3250.0
    assert cabin["co2_raw_unit"] == "ppm"


def _mock_eda(router: respx.MockRouter, *, radiation_status: int = 200) -> None:
    m = osdr.MISSION
    router.get(f"{BASE}/missions/").respond(json=_fx("eda/missions.json"))
    router.get(f"{BASE}/missions/{m}/temperature/iss/").respond(
        json=_fx(f"eda/temperature_iss_{m}.json")
    )
    router.get(f"{BASE}/missions/{m}/humidity/iss/").respond(json=_fx(f"eda/humidity_iss_{m}.json"))
    router.get(f"{BASE}/missions/{m}/co2/iss/").respond(json=_fx(f"eda/co2_iss_{m}.json"))
    if radiation_status == 200:
        router.get(f"{BASE}/missions/{m}/radiation_data/").respond(
            json=_fx(f"eda/radiation_data_{m}.json")
        )
    else:
        router.get(f"{BASE}/missions/{m}/radiation_data/").respond(radiation_status)


@pytest.mark.asyncio
async def test_snapshot_wrapper():
    with respx.mock(assert_all_called=False) as router:
        _mock_eda(router)
        async with httpx.AsyncClient() as client:
            snap = await osdr.fetch_snapshot(osdr.MISSION, client=client, now=NOW)
    assert snap["fetched_at"] == "2026-11-14T10:00:00Z"
    assert snap["mission"] == osdr.MISSION
    assert any(u.endswith("/radiation_data/") for u in snap["source_urls"])
    assert len(snap["source_urls"]) == 5
    for k in ("temperature_c", "rh_pct"):
        assert snap["cabin"][k]["n"] == 73
    assert snap["cabin"]["co2_raw_unit"] == "ppm"
    assert snap["dose"]["source"] == "eda"
    assert snap["dose"]["raw_unit"] == "mGy/day (one value per day, summed)"
    assert snap["dose"]["absorbed_mgy"] == pytest.approx(snap["dose"]["raw_sum"], abs=1e-3)
    assert snap["dose"]["absorbed_mgy_per_day"] == pytest.approx(
        snap["dose"]["raw_sum"] / 49, abs=1e-3
    )
    assert "effective_msv" not in json.dumps(snap)


@pytest.mark.asyncio
async def test_radlab_fallback(monkeypatch):
    monkeypatch.setattr(osdr, "RADLAB_UNIT_CONFIRMED", False)
    radlab = {
        "columns": ["timestamp", "instrument_id", "absorbed_dose_rate"],
        "index": [],
        "data": [
            ["2017-12-16T00:00:00", "DosTel1", 10.0],
            ["2017-12-16T01:00:00", "DosTel1", 12.0],
            ["2017-12-16T02:00:00", "DosTel1", 14.0],
        ],
    }
    with respx.mock(assert_all_called=False) as router:
        _mock_eda(router, radiation_status=404)
        router.get(url__startswith=osdr.RADLAB_URL).respond(json=radlab)
        async with httpx.AsyncClient() as client:
            snap = await osdr.fetch_snapshot(osdr.MISSION, client=client, now=NOW)
    dose = snap["dose"]
    assert dose["source"] == "radlab"
    assert dose["raw_sum"] == 36.0
    assert dose["raw_unit"] == osdr.RADLAB_UNIT
    assert dose["absorbed_mgy"] is None and dose["absorbed_mgy_per_day"] is None


def test_failure_keeps_previous_snapshot(tmp_path):
    out = tmp_path / "snap.json"
    out.write_bytes(b'{"keep": "me"}\n')
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/missions/").respond(500)
        code = osdr.main(["--mission", osdr.MISSION, "--out", str(out)])
    assert code == 1
    assert out.read_bytes() == b'{"keep": "me"}\n'
