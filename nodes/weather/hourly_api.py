"""Hourly outdoor values from a public weather API (D45 §4.2, plan Task 9).

The API and its URL are named only in DATA_SOURCES.md ("Earth weather"); the code reads the URL from
WEATHER_API_URL. Its past hours are archived weather-model values, not station observations, and the
console labels them so. The request carries only the coarse cell; the URL and the cell are never
logged, printed or put in an error message.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import httpx

from nodes.weather.mapper import HourRow

HOURLY = ("temperature_2m", "relative_humidity_2m", "surface_pressure")
UNITS = {"temperature_2m": "°C", "relative_humidity_2m": "%", "surface_pressure": "hPa"}
USER_AGENT = "habitat-hub-weather/1"
MAX_PAST_DAYS = 92
TIMEOUT_S = 10


class WeatherApiError(RuntimeError):
    pass


def parse(data: dict) -> list[HourRow]:
    """HourRows from a response with unixtime hours. A null value stays None; other units are refused."""
    units = data.get("hourly_units") or {}
    for var, unit in UNITS.items():
        if units.get(var) != unit:
            raise WeatherApiError(f"unexpected unit for {var}: {units.get(var)!r}")
    if units.get("time") != "unixtime":
        raise WeatherApiError("unexpected time unit: ask for timeformat=unixtime")
    h = data.get("hourly") or {}
    times = h.get("time") or []
    cols = [h.get(v) or [None] * len(times) for v in HOURLY]
    rows = []
    for i, t in enumerate(times):
        vals = [c[i] if i < len(c) else None for c in cols]
        temp, rh, p = (None if v is None else float(v) for v in vals)
        rows.append(HourRow(datetime.fromtimestamp(int(t), UTC), temp, rh, p))
    rows.sort(key=lambda r: r.t)
    return rows


class HourlyApi:
    """Provider: the rows of [start, end] for the coarse cell (lat, lon)."""

    def __init__(
        self, url: str, lat: float, lon: float, *, http: httpx.Client | None = None
    ) -> None:
        self.url, self.lat, self.lon = url, lat, lon
        self.http = http or httpx.Client(timeout=TIMEOUT_S)

    def hours(self, start: datetime, end: datetime) -> list[HourRow]:
        now = datetime.now(UTC)
        past = min(MAX_PAST_DAYS, max(1, math.ceil((now - start) / timedelta(days=1))))
        params = {
            "latitude": self.lat, "longitude": self.lon, "hourly": ",".join(HOURLY),
            "past_days": past, "forecast_days": 1, "timeformat": "unixtime", "timezone": "GMT",
        }  # fmt: skip
        try:
            res = self.http.get(self.url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as e:
            raise WeatherApiError(f"weather API unreachable ({type(e).__name__})") from None
        if res.status_code != 200:
            raise WeatherApiError(f"weather API answered HTTP {res.status_code}")
        try:
            data = res.json()
        except ValueError:
            raise WeatherApiError("weather API answered with no JSON") from None
        return [r for r in parse(data) if start <= r.t <= end]
