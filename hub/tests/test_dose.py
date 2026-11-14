import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from hub.nasa.dose import DoseWriter, estimate_dose, load_dose_profile, mission_day

METHOD = "mission_day × 0.5 mSv/day (upper ISS effective-dose rate, NTRS 20250006168); estimate, not measured"
RAW = {
    "profile": "p",
    "mission_start": "2026-05-19",
    "rate_msv_per_day": 0.5,
    "rate_ref": "NTRS 20250006168",
    "rate_url": "u",
    "method": METHOD,
    "career_limit_msv": 600,
    "career_limit_ref": "NASA-STD-3001 Vol 1 Rev C [V1 4030]",
}
TODAY = date(2026, 11, 14)


def _profile(tmp_path, **over):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({**RAW, **over}))
    return load_dose_profile(p)


class FakeIngestor:
    def __init__(self, status="ok"):
        self.status = status
        self.readings = []

    def ingest_internal(self, r):
        self.readings.append(r)
        return SimpleNamespace(results=[SimpleNamespace(ind="rad_dose_cum", status=self.status)])


def test_mission_day():
    assert mission_day(TODAY, date(2026, 5, 19)) == 180
    assert mission_day(TODAY, TODAY) == 1
    assert mission_day(date(2026, 11, 13), TODAY) == 0


def test_estimate(tmp_path):
    e = estimate_dose(_profile(tmp_path), TODAY)
    assert e.effective_msv == 90.0 and e.career_fraction == 0.15
    assert e.effective_msv_method == METHOD


@pytest.mark.parametrize("key", ["rate_ref", "method"])
def test_profile_requires_field(tmp_path, key):
    with pytest.raises(ValueError):
        _profile(tmp_path, **{key: ""})


def test_committed_profile_loads():
    from pathlib import Path

    p = load_dose_profile(Path(__file__).resolve().parents[2] / "data/nasa/dose_profile.json")
    assert p.method == METHOD


@pytest.mark.asyncio
async def test_tick_writes_reading(tmp_path):
    ing = FakeIngestor()
    w = DoseWriter(_profile(tmp_path), ing)
    await w.tick(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
    (r,) = ing.readings
    assert (r.node, r.boot, r.seq, r.ind, r.val, r.unit, r.src, r.dev, r.q, r.crew) == (
        "nasa",
        0,
        1794657600001,
        "rad_dose_cum",
        90.0,
        "mSv",
        "nasa",
        "OSDR",
        ("ok",),
        None,
    )
    assert w.last_status == "ok"


@pytest.mark.asyncio
async def test_tick_once_per_mission_day(tmp_path):
    ing = FakeIngestor()
    w = DoseWriter(_profile(tmp_path), ing)
    await w.tick(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
    await w.tick(datetime(2026, 11, 14, 12, 10, tzinfo=UTC))
    assert len(ing.readings) == 1
    await w.tick(datetime(2026, 11, 15, 0, 0, tzinfo=UTC))
    assert [r.val for r in ing.readings] == [90.0, 90.5]


@pytest.mark.asyncio
async def test_status_from_hub(tmp_path):
    w = DoseWriter(_profile(tmp_path), FakeIngestor("act"))
    await w.tick(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
    assert w.last_status == "act"


@pytest.mark.asyncio
async def test_no_ingestor_status_unknown(tmp_path):
    w = DoseWriter(_profile(tmp_path), None)
    await w.tick(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
    assert w.last is not None and w.last_status == "unknown"
