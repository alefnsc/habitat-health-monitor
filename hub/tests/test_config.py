from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from hub.config import FEATURE_NAMES, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_defaults():
    s = load_settings({})
    assert s.db_path == Path("var/hub.db")
    assert s.mqtt_host == "127.0.0.1"
    assert s.mqtt_port == 1883
    assert s.mqtt_user is None
    assert s.mqtt_pass is None
    assert s.serial_port is None
    assert s.serial_baud == 250000
    assert s.thresholds_path == Path("data/thresholds.json")
    assert s.guidance_path == Path("data/guidance.json")
    assert s.food_catalog_path == Path("data/food/catalog.json")
    assert s.food_thresholds_path == Path("data/food/thresholds_food.json")
    assert s.food_references_path == Path("data/food/references.json")
    assert s.console_dist == Path("console/dist")
    assert s.camera_dist == Path("camera/dist")
    assert s.crews == ["crew-a", "crew-b", "crew-c"]
    assert s.morning_at == time(7, 0)
    assert s.tz == "America/Sao_Paulo"
    assert s.http_host == "0.0.0.0"
    assert s.http_port == 8000
    assert s.cors_origins == ["*"]
    assert s.features == {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food", "signals"}
    assert s.features == FEATURE_NAMES
    assert s.linksim_url == "http://127.0.0.1:8200"
    assert s.link_config == Path("linksim/link.json")


def test_overrides():
    s = load_settings(
        {
            "HUB_HTTP_PORT": "9000",
            "HUB_CREWS": "crew-a,crew-b",
            "HUB_SERIAL_PORT": "/dev/ttyACM0",
            "HUB_MORNING_AT": "06:30",
            "HUB_FEATURES": "nasa,serial",
            "HUB_CAMERA_DIST": "/tmp/cam",
            "HUB_FOOD_CATALOG": "/tmp/food/c.json",
            "HUB_FOOD_THRESHOLDS": "/tmp/food/t.json",
            "HUB_FOOD_REFERENCES": "/tmp/food/r.json",
        }
    )
    assert s.http_port == 9000
    assert s.crews == ["crew-a", "crew-b"]
    assert s.serial_port == "/dev/ttyACM0"
    assert s.morning_at == time(6, 30)
    assert s.features == {"nasa", "serial"}
    assert s.camera_dist == Path("/tmp/cam")
    assert s.food_catalog_path == Path("/tmp/food/c.json")
    assert s.food_thresholds_path == Path("/tmp/food/t.json")
    assert s.food_references_path == Path("/tmp/food/r.json")


def test_empty_features():
    assert load_settings({"HUB_FEATURES": ""}).features == frozenset()


def test_food_feature():
    assert load_settings({"HUB_FEATURES": "food"}).features == {"food"}
    with pytest.raises(ValueError, match="warp"):
        load_settings({"HUB_FEATURES": "food,warp"})


def test_bad_int():
    with pytest.raises(ValueError, match="HUB_HTTP_PORT"):
        load_settings({"HUB_HTTP_PORT": "abc"})


def test_unknown_crew():
    with pytest.raises(ValueError, match="crew-z"):
        load_settings({"HUB_CREWS": "crew-a,crew-z"})


def test_unknown_feature():
    with pytest.raises(ValueError, match="warp"):
        load_settings({"HUB_FEATURES": "nasa,warp"})


def test_fake_clock(clock):
    clock.set(datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC))
    clock.advance(1.5)
    now = clock()
    assert now == datetime(2026, 11, 14, 12, 0, 1, 500000, tzinfo=UTC)
    assert now.tzinfo == UTC


def test_links_file():
    text = (REPO_ROOT / "docs" / "decisions" / "links.md").read_text(encoding="utf-8")
    for url in (
        "https://github.com/alefnsc/habitat-health-monitor",
        "https://alefnsc.github.io/habitat-health-monitor/",
        "https://github.com/alefnsc/ground-truth",
    ):
        assert url in text
    assert "<" not in text


def test_settings_fixture(settings, tmp_path):
    assert settings.db_path.parent == tmp_path
    assert not settings.thresholds_path.exists()
    assert not settings.guidance_path.exists()
    assert not settings.food_catalog_path.exists()
