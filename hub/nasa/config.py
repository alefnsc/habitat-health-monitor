"""NASA gateway settings (task N1). Read from the environment; no secret is ever stored."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_DONKI_BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"


@dataclass(frozen=True)
class NasaSettings:
    api_key: str | None = None
    donki_base: str = DEFAULT_DONKI_BASE
    donki_mode: Literal["live", "replay"] = "live"
    var_dir: Path = Path("var")
    replay_path: Path = Path("data/nasa/donki_replay_2025-11.json")
    isslive_capture: Path = Path("data/nasa/isslive_capture.jsonl")
    dose_profile_path: Path = Path("data/nasa/dose_profile.json")
    osdr_snapshot_path: Path = Path("data/nasa/osdr_eda_snapshot.json")


def load_nasa_settings(env: Mapping[str, str]) -> NasaSettings:
    def get(name: str) -> str | None:
        v = env.get(name, "").strip()
        return v or None

    mode = get("DONKI_MODE") or "live"
    if mode not in ("live", "replay"):
        raise ValueError(f"DONKI_MODE must be 'live' or 'replay', got {mode!r}")
    base = (get("DONKI_BASE") or DEFAULT_DONKI_BASE).rstrip("/")
    var_dir = get("HUB_VAR_DIR")
    return NasaSettings(
        api_key=get("NASA_API_KEY"),
        donki_base=base,
        donki_mode=mode,  # type: ignore[arg-type]
        var_dir=Path(var_dir) if var_dir else Path("var"),
    )
