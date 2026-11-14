"""N10: HRP risk pages scraped once into data/nasa/hrp_risks.json."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from hub.contract import INTAKE_INDS
from hub.nasa import hrp_scrape as hrp

FIX = Path(__file__).parent / "fixtures" / "hrp"


def _html(name: str) -> str:
    return (FIX / name).read_text()


def test_index_lists_22_one_inactive():
    refs = hrp.parse_index(_html("risks_index.html"))
    assert len(refs) == 22
    assert sum(1 for r in refs if not r.active) == 1
    ids = {r.id for r in refs}
    assert {100, 96, 77, 179, 105, 180, 99, 176, 81} <= ids


def test_sleep_ratings():
    r = hrp.parse_risk(_html("risk_100.html"), 100, "u")
    assert "Sleep" in r.title
    assert len(r.ratings) == 8
    assert {x.operations_lxc for x in r.ratings} == {"5x2"}
    mars = [x for x in r.ratings if x.mission_category == "Mars"]
    assert any(x.operations_disposition == "Requires Mitigation" for x in mars)


def test_carcinogenesis_dates():
    r = hrp.parse_risk(_html("risk_96.html"), 96, "u")
    assert r.last_published == "08/17/26"
    assert r.board_approved is None


def test_sleep_board_approved():
    r = hrp.parse_risk(_html("risk_100.html"), 100, "u")
    assert r.board_approved == "3/2022"


def test_sans_mars():
    r = hrp.parse_risk(_html("risk_105.html"), 105, "u")
    row = next(x for x in r.ratings if "Planetary" in x.duration)
    assert row.mission_category == "Mars"
    assert row.operations_lxc == "4x4" and row.long_term_lxc == "4x5"


def test_indicator_map_complete():
    ids = {r.id for r in hrp.parse_index(_html("risks_index.html"))}
    for ind in (
        "hr",
        "bp_sys",
        "bp_dia",
        "glucose",
        "body_temp",
        "sleep_h",
        "mood",
        "space_weather",
        "rad_dose_cum",
    ):
        assert hrp.INDICATOR_RISKS[ind], ind
    for risk_ids in hrp.INDICATOR_RISKS.values():
        assert set(risk_ids) <= ids


def test_intake_and_body_mass_map_to_nutrition():
    index = hrp.parse_index(_html("risks_index.html"))
    assert "Nutrition" in next(r for r in index if r.id == 176).title
    assert len(INTAKE_INDS) == 10
    for ind in [*INTAKE_INDS, "body_mass"]:
        assert hrp.INDICATOR_RISKS[ind] == [176]
    assert hrp.INDICATOR_RISKS["intake_water_ml"] == [176]


@pytest.mark.asyncio
async def test_output_wrapper():
    now = datetime(2026, 11, 14, 11, 0, tzinfo=UTC)
    with respx.mock(assert_all_called=False) as router:
        router.get(hrp.INDEX_URL).respond(text=_html("risks_index.html"))
        for i in (100, 96, 105):
            router.get(f"{hrp.RISK_URL}?i={i}").respond(text=_html(f"risk_{i}.html"))
        router.get(url__startswith=hrp.RISK_URL).respond(404)
        async with httpx.AsyncClient() as client:
            out = await hrp.scrape(client, now=now, delay_s=0)
    assert out["scraped_at"] == "2026-11-14T11:00:00Z"
    assert out["source"] == "https://humanresearchroadmap.nasa.gov/Risks/"
    assert len(out["risks"]) == 21
    sleep = next(r for r in out["risks"] if r["id"] == 100)
    assert len(sleep["ratings"]) == 8
    failed = next(r for r in out["risks"] if r["id"] == 99)
    assert failed["ratings"] == []
    assert out["indicator_map"]["body_mass"] == [176]
    assert "not personal probabilities" in out["note"]
    json.dumps(out)
