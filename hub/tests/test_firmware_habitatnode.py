"""HabitatNode library host tests (ring, format, boot log, MQTT link), compiled and run here.

Until 15/11 they only ran by hand. They need a C++ compiler and ArduinoJson (header-only).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "firmware" / "libraries" / "HabitatNode"
TESTS = sorted((LIB / "test").glob("test_*.cpp"))


def _arduinojson() -> Path | None:
    env = os.environ.get("ARDUINOJSON_SRC")
    for p in (
        Path(env) if env else None,
        Path.home() / "Documents/Arduino/libraries/ArduinoJson/src",
        Path.home() / "Arduino/libraries/ArduinoJson/src",
    ):
        if p is not None and (p / "ArduinoJson.h").is_file():
            return p
    return None


def test_every_library_test_is_found() -> None:
    assert {t.name for t in TESTS} >= {
        "test_ring.cpp",
        "test_format.cpp",
        "test_boot.cpp",
        "test_link.cpp",
    }


def test_node_loop_runs_the_host_tested_link() -> None:
    # MqttLink.h is what test_link.cpp drives on the host; an Arduino call in it would break that.
    text = (LIB / "src" / "MqttLink.h").read_text()
    assert "Arduino.h" not in text and "Serial." not in text
    assert "link_.loop(" in (LIB / "src" / "HabitatNode.cpp").read_text()


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
@pytest.mark.parametrize("src", TESTS, ids=lambda p: p.stem)
def test_library_host_test(src: Path, tmp_path: Path) -> None:
    aj = _arduinojson()
    if aj is None:
        pytest.skip("ArduinoJson not installed")
    exe = tmp_path / src.stem
    build = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Werror", "-I", str(LIB / "src"), "-I", str(aj),
         str(LIB / "src" / "ReadingFormat.cpp"), str(src), "-o", str(exe)],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe)], check=False, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip().endswith("ok")
