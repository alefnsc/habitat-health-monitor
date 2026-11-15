"""The weather provider seam (D45 §4.2). The provider itself is the team owner's choice (spec §13);
until it is chosen, default_provider refuses to run, so nothing is fetched by accident."""

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
        raise RuntimeError("no weather provider chosen yet (D45 §13); see DATA_SOURCES.md")


def default_provider(lat: float, lon: float) -> Provider:
    return NoProvider()
