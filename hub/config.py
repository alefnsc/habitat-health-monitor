"""Hub settings, read only from HUB_* environment variables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path

FEATURE_NAMES: frozenset[str] = frozenset(
    {"nasa", "iss", "wearable", "mcp", "ble", "serial", "food"}
)
KNOWN_CREWS: tuple[str, ...] = ("crew-a", "crew-b", "crew-c")


@dataclass(frozen=True)
class Settings:
    # Storage and broker
    db_path: Path
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    # Serial
    serial_port: str | None
    serial_baud: int
    # Data files
    thresholds_path: Path
    guidance_path: Path
    food_catalog_path: Path
    food_thresholds_path: Path
    food_references_path: Path
    # Static builds
    console_dist: Path
    camera_dist: Path
    # Crew and prompts
    crews: list[str]
    morning_at: time
    tz: str
    # HTTP
    http_host: str
    http_port: int
    cors_origins: list[str]
    # Features and link
    features: frozenset[str]
    linksim_url: str
    link_config: Path


def _str(env: Mapping[str, str], key: str, default: str) -> str:
    return env.get(key, default)


def _opt(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    return value if value else None


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from None


def _path(env: Mapping[str, str], key: str, default: str) -> Path:
    return Path(env.get(key) or default)


def _list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _time(env: Mapping[str, str], key: str, default: time) -> time:
    raw = env.get(key)
    if not raw:
        return default
    try:
        hh, mm = raw.split(":")
        return time(int(hh), int(mm))
    except ValueError:
        raise ValueError(f"{key} must be HH:MM, got {raw!r}") from None


def _crews(env: Mapping[str, str]) -> list[str]:
    raw = env.get("HUB_CREWS")
    crews = list(KNOWN_CREWS) if raw is None else _list(raw)
    unknown = [c for c in crews if c not in KNOWN_CREWS]
    if unknown:
        raise ValueError(f"HUB_CREWS has unknown crew ids: {', '.join(unknown)}")
    return crews


def _features(env: Mapping[str, str]) -> frozenset[str]:
    raw = env.get("HUB_FEATURES")
    if raw is None:
        return FEATURE_NAMES
    features = frozenset(_list(raw))
    unknown = sorted(features - FEATURE_NAMES)
    if unknown:
        raise ValueError(f"HUB_FEATURES has unknown features: {', '.join(unknown)}")
    return features


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build Settings from a mapping of HUB_* variables (usually os.environ)."""
    return Settings(
        db_path=_path(env, "HUB_DB", "var/hub.db"),
        mqtt_host=_str(env, "HUB_MQTT_HOST", "127.0.0.1"),
        mqtt_port=_int(env, "HUB_MQTT_PORT", 1883),
        mqtt_user=_opt(env, "HUB_MQTT_USER"),
        mqtt_pass=_opt(env, "HUB_MQTT_PASS"),
        serial_port=_opt(env, "HUB_SERIAL_PORT"),
        serial_baud=_int(env, "HUB_SERIAL_BAUD", 250000),
        thresholds_path=_path(env, "HUB_THRESHOLDS", "data/thresholds.json"),
        guidance_path=_path(env, "HUB_GUIDANCE", "data/guidance.json"),
        food_catalog_path=_path(env, "HUB_FOOD_CATALOG", "data/food/catalog.json"),
        food_thresholds_path=_path(env, "HUB_FOOD_THRESHOLDS", "data/food/thresholds_food.json"),
        food_references_path=_path(env, "HUB_FOOD_REFERENCES", "data/food/references.json"),
        console_dist=_path(env, "HUB_CONSOLE_DIST", "console/dist"),
        camera_dist=_path(env, "HUB_CAMERA_DIST", "camera/dist"),
        crews=_crews(env),
        morning_at=_time(env, "HUB_MORNING_AT", time(7, 0)),
        tz=_str(env, "HUB_TZ", "America/Sao_Paulo"),
        http_host=_str(env, "HUB_HTTP_HOST", "0.0.0.0"),
        http_port=_int(env, "HUB_HTTP_PORT", 8000),
        cors_origins=_list(env.get("HUB_CORS_ORIGINS", "*")),
        features=_features(env),
        linksim_url=_str(env, "HUB_LINKSIM_URL", "http://127.0.0.1:8200"),
        link_config=_path(env, "HUB_LINK_CONFIG", "linksim/link.json"),
    )
