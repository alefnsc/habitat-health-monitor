"""The hourly weather API adapter (D45 plan Task 9). The fixture is a real response recorded at a
neutral point (0, 0), with location fields removed and one value set to null by hand."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from nodes.weather.hourly_api import HourlyApi, WeatherApiError, parse
from nodes.weather.mapper import HourRow
from nodes.weather.provider import NoProvider, default_provider

FIX = Path(__file__).parent / "fixtures" / "hourly-api-sample.json"
URL = "https://weather.example/v1/forecast"


def sample() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_sample_parses_to_utc_hour_rows_in_order():
    rows = parse(sample())
    assert len(rows) == 12 and all(isinstance(r, HourRow) and r.t.tzinfo == UTC for r in rows)
    assert [r.t for r in rows] == sorted(r.t for r in rows)
    assert rows[0].t == datetime.fromtimestamp(sample()["hourly"]["time"][0], UTC)
    r = rows[0]
    assert -90 < r.temp_c < 60 and 0 <= r.rh_pct <= 100 and 850 < r.p_hpa < 1090


def test_a_null_value_stays_missing():
    rows = parse(sample())
    assert (
        rows[5].temp_c is None and rows[5].rh_pct is not None
    )  # set to null by hand in the fixture


def test_units_other_than_c_percent_hpa_are_refused():
    data = sample()
    data["hourly_units"]["surface_pressure"] = "kPa"
    with pytest.raises(WeatherApiError, match="unit"):
        parse(data)


def test_the_fixture_holds_no_location():
    text = FIX.read_text(encoding="utf-8")
    for key in ('"latitude"', '"longitude"', '"elevation"', '"timezone"'):
        assert key not in text


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_hours_asks_for_the_past_days_and_keeps_only_the_range():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params), ua=req.headers["user-agent"])
        return httpx.Response(200, json=sample())

    rows_all = parse(sample())
    start, end = rows_all[2].t, rows_all[8].t
    api = HourlyApi(URL, -23.6, -46.7, http=client(handler))
    rows = api.hours(start, end)
    assert [r.t for r in rows] == [r.t for r in rows_all[2:9]]
    assert seen["latitude"] == "-23.6" and seen["longitude"] == "-46.7"
    assert seen["hourly"] == "temperature_2m,relative_humidity_2m,surface_pressure"
    assert seen["timeformat"] == "unixtime" and seen["timezone"] == "GMT"
    assert int(seen["past_days"]) >= 1 and seen["forecast_days"] == "1"
    assert seen["ua"] == "habitat-hub-weather/1"


def test_an_http_error_names_the_status_but_never_the_url_or_location():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": True, "reason": "bad"})

    api = HourlyApi(URL, -23.6, -46.7, http=client(handler))
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    with pytest.raises(WeatherApiError) as e:
        api.hours(now - timedelta(hours=6), now)
    text = str(e.value)
    assert (
        "400" in text
        and "weather.example" not in text
        and "-23.6" not in text
        and "46.7" not in text
    )


def test_default_provider_needs_the_api_url():
    assert isinstance(default_provider(-23.6, -46.7, None), NoProvider)
    assert isinstance(default_provider(-23.6, -46.7, URL), HourlyApi)
