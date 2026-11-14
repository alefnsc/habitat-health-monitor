import json
from pathlib import Path

import pytest

from linksim.config import Blackout, ConfigError, hold_seconds, in_blackout, load_config

HERE = Path(__file__).resolve().parent.parent


def _write(tmp_path: Path, **kw) -> Path:
    data = {"light_time_s": 720, "time_scale": 60, "blackouts": []}
    data.update(kw)
    data = {k: v for k, v in data.items() if v is not None}
    p = tmp_path / "link.json"
    p.write_text(json.dumps(data))
    return p


def test_default_file():
    cfg = load_config(HERE / "link.json")
    assert cfg.light_time_s == 720
    assert cfg.time_scale == 60
    assert cfg.blackouts == []
    assert hold_seconds(cfg) == 12.0


def test_real_scale(tmp_path):
    assert hold_seconds(load_config(_write(tmp_path, time_scale=1))) == 720.0


def test_demo_file():
    cfg = load_config(HERE / "link.demo.json")
    assert cfg.blackouts == [Blackout(30, 60)]
    assert cfg.light_time_s == 720 and cfg.time_scale == 60


def test_missing_time_scale(tmp_path):
    with pytest.raises(ConfigError, match="time_scale"):
        load_config(_write(tmp_path, time_scale=None))


def test_scale_below_one(tmp_path):
    with pytest.raises(ConfigError, match="time_scale"):
        load_config(_write(tmp_path, time_scale=0))


def test_light_time_cap(tmp_path):
    with pytest.raises(ConfigError, match="light_time_s"):
        load_config(_write(tmp_path, light_time_s=1500))


def test_blackout_reversed(tmp_path):
    with pytest.raises(ConfigError, match=r"blackouts\[0\]"):
        load_config(_write(tmp_path, blackouts=[{"start": 60, "end": 30}]))


def test_blackout_overlap(tmp_path):
    with pytest.raises(ConfigError, match="overlap"):
        load_config(
            _write(tmp_path, blackouts=[{"start": 0, "end": 40}, {"start": 30, "end": 60}])
        )


def test_in_blackout_half_open():
    cfg = load_config(HERE / "link.demo.json")
    assert in_blackout(cfg, 29.99) is None
    assert in_blackout(cfg, 30.0) == Blackout(30, 60)
    assert in_blackout(cfg, 59.99) == Blackout(30, 60)
    assert in_blackout(cfg, 60.0) is None
