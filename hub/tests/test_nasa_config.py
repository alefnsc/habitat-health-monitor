from pathlib import Path

import pytest

from hub.nasa.config import load_nasa_settings


def test_settings_defaults():
    s = load_nasa_settings({})
    assert s.api_key is None
    assert s.donki_mode == "live"
    assert s.var_dir == Path("var")
    assert s.donki_base == "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
    assert s.replay_path == Path("data/nasa/donki_replay_2025-11.json")
    assert s.isslive_capture == Path("data/nasa/isslive_capture.jsonl")
    assert s.dose_profile_path == Path("data/nasa/dose_profile.json")
    assert s.osdr_snapshot_path == Path("data/nasa/osdr_eda_snapshot.json")


def test_blank_key_is_none():
    assert load_nasa_settings({"NASA_API_KEY": ""}).api_key is None
    assert load_nasa_settings({"NASA_API_KEY": "  "}).api_key is None


def test_env_overrides():
    s = load_nasa_settings(
        {
            "NASA_API_KEY": "k",
            "DONKI_BASE": "http://x/get/",
            "DONKI_MODE": "replay",
            "HUB_VAR_DIR": "/tmp/v",
        }
    )
    assert (s.api_key, s.donki_base, s.donki_mode, s.var_dir) == (
        "k",
        "http://x/get",
        "replay",
        Path("/tmp/v"),
    )


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        load_nasa_settings({"DONKI_MODE": "demo"})
