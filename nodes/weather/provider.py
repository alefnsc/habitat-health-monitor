"""The weather provider seam (D45 §4.2). The hourly API is used once WEATHER_API_URL is set (its value
is in DATA_SOURCES.md, "Earth weather"); without it, default_provider refuses, so nothing is fetched
by accident."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nodes.weather.mapper import HourRow


class Provider(Protocol):
    def hours(self, start: datetime, end: datetime) -> list[HourRow]:
        """Observed hourly rows in [start, end], oldest first; missing values are None."""
        ...


class NoProvider:
    def hours(self, start: datetime, end: datetime) -> list[HourRow]:
        raise RuntimeError("no weather provider: set WEATHER_API_URL (see DATA_SOURCES.md)")


def default_provider(lat: float, lon: float, url: str | None) -> Provider:
    if not url:
        return NoProvider()
    from nodes.weather.hourly_api import HourlyApi

    return HourlyApi(url, lat, lon)
