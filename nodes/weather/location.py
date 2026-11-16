"""The bench location as a coarse grid cell (D45 §4.2). Read from WEATHER_LAT / WEATHER_LON in the
environment or .env; rounded to 1 decimal (about 11 km) before any use; never logged or posted."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

DECIMALS = 1


class LocationError(ValueError):
    pass


def env_file_values(path: Path) -> dict[str, str]:
    """KEY=value lines of a .env file; a missing file gives {}."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def coarse_location(env: Mapping[str, str], dotenv: Mapping[str, str]) -> tuple[float, float]:
    """(lat, lon) rounded to DECIMALS. The environment wins over .env."""
    raw = {k: env.get(k) or dotenv.get(k) for k in ("WEATHER_LAT", "WEATHER_LON")}
    if not raw["WEATHER_LAT"] or not raw["WEATHER_LON"]:
        raise LocationError("set WEATHER_LAT and WEATHER_LON (in .env, never committed)")
    try:
        lat, lon = float(raw["WEATHER_LAT"]), float(raw["WEATHER_LON"])
    except ValueError:
        raise LocationError("WEATHER_LAT and WEATHER_LON must be numbers") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise LocationError("WEATHER_LAT or WEATHER_LON is out of range")
    return round(lat, DECIMALS), round(lon, DECIMALS)
