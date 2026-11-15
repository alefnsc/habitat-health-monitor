"""Tilt node checks that need no board: pin map, names, safety notes, host tests (D39)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hub.assess import UNGATED_INDS
from hub.contract import DEVICES, INDICATORS, NODES

FW = Path(__file__).resolve().parents[2] / "firmware"
DIR = FW / "tilt-esp8266"
SKETCH = DIR / "tilt-esp8266.ino"


def test_sketch_pin_names_and_timing() -> None:
    text = SKETCH.read_text()
    assert "PIN_TILT = 14" in text  # D5 on the NodeMCU Amica
    assert 'node.begin("tilt-1")' in text
    assert "habitat::IND_TILT" in text and "habitat::DEV_KY017" in text
    assert "kDebounceMs = 200" in text and "kHeartbeatMs = 10000" in text
    assert "tilt-1" in NODES and "KY017" in DEVICES and INDICATORS["tilt"] == "state"
    assert "tilt" in UNGATED_INDS


def test_firmware_tables_carry_tilt() -> None:
    h = (FW / "libraries/HabitatNode/src/ReadingFormat.h").read_text()
    cpp = (FW / "libraries/HabitatNode/src/ReadingFormat.cpp").read_text()
    assert "IND_TILT, IND_COUNT" in h and "DEV_KY017, DEV_RING, DEV_COUNT" in h
    assert '"tilt"' in cpp and '"state"' in cpp and '"KY017"' in cpp


def tracked_files(d: Path) -> list[Path]:
    """Files git tracks under d. A local, git-ignored secrets.h is not repository content."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "."], cwd=d, check=True, capture_output=True, text=True
    ).stdout
    return [d / p for p in out.split("\0") if p]


def test_readme_safety_and_no_company_name() -> None:
    readme = (DIR / "README.md").read_text().lower()
    for word in ("sealed", "adult", "mercury", "reads 0", "d5"):
        assert word in readme, word
    files = tracked_files(DIR)
    assert SKETCH in files and DIR / "secrets.h" not in files
    for f in files:
        assert "vocaid" not in f.read_text(errors="ignore").lower(), f
    assert (DIR / "secrets.example.h").exists()


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
def test_tilt_pure_block_host_tests() -> None:
    r = subprocess.run(
        [str(DIR / "test/run_host_tests.sh")], check=False, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("ok")


def test_safety_checklist_has_mercury_and_magnet_rules() -> None:
    text = (FW.parent / "docs" / "safety-checklist.md").read_text()
    assert "12. **Mercury tilt switch (KY-017" in text
    assert "13. **Neodymium magnets" in text
    low = text.lower()
    assert "hazardous-waste" in low and "no vacuum" in low and "under 18" in low


def test_boot_counter_is_an_append_only_flash_log() -> None:
    # Bench 2026-11-15: the EEPROM emulation's erase-then-write per boot lost or reverted the
    # count (boots 4, 7, 9, 8, 10, 11, 1, 2). The ESP8266 branch now uses BootLog.h.
    cpp = (FW / "libraries/HabitatNode/src/HabitatNode.cpp").read_text()
    assert "BootLog::bump" in cpp and "#include <EEPROM.h>" not in cpp
    assert (FW / "libraries/HabitatNode/src/BootLog.h").is_file()
    assert "test_boot.cpp" in (DIR / "test/run_host_tests.sh").read_text()
