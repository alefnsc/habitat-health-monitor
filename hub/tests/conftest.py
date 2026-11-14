from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from hub.config import Settings, load_settings


class FakeClock:
    """Settable UTC clock for tests. Call it to read the time."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def set(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = dt.astimezone(UTC)

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path) -> Settings:
    missing = tmp_path / "missing"
    return replace(
        load_settings({}),
        db_path=tmp_path / "hub.db",
        mqtt_host="",  # no subscriber unless a test sets a host
        console_dist=missing / "console",
        camera_dist=missing / "camera",
        thresholds_path=missing / "thresholds.json",
        guidance_path=missing / "guidance.json",
        food_catalog_path=missing / "food" / "catalog.json",
        food_thresholds_path=missing / "food" / "thresholds_food.json",
        food_references_path=missing / "food" / "references.json",
        link_config=missing / "link.json",
    )
