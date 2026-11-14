"""Exercise-rig firmware checks that need no board: Wokwi twin sync, diagram sanity, host tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FW = Path(__file__).resolve().parents[2] / "firmware"
SKETCH = FW / "exercise-uno" / "exercise-uno.ino"
TWIN = FW / "wokwi" / "uno-rig"

# Pin names from docs.wokwi.com/parts/<type>, read 2026-11-14.
PART_PINS = {
    "wokwi-hx711": {"VCC", "DT", "SCK", "GND"},
    "wokwi-servo": {"PWM", "V+", "GND"},
    "wokwi-buzzer": {"1", "2"},
    "wokwi-ntc-temperature-sensor": {"VCC", "OUT", "GND"},
    "wokwi-potentiometer": {"VCC", "SIG", "GND"},
}
UNO_PINS = {"5V", "GND.1", "GND.2", "GND.3", "A0", "A1"} | {str(i) for i in range(14)}


def test_twin_sketch_is_byte_identical_to_exercise_uno() -> None:
    assert (TWIN / "sketch.ino").read_bytes() == SKETCH.read_bytes(), (
        "run firmware/wokwi/uno-rig/sync.sh"
    )


def test_twin_diagram_parts_and_pins() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    parts = {p["id"]: p for p in d["parts"]}
    assert len(parts) == len(d["parts"]), "duplicate part ids"
    assert {p["type"] for p in d["parts"]} >= {"wokwi-arduino-uno", *PART_PINS, "wokwi-text"}
    for a, b, *_ in d["connections"]:
        for end in (a, b):
            pid, pin = end.split(":", 1)
            assert pid in parts, end
            t = parts[pid]["type"]
            allowed = UNO_PINS if t == "wokwi-arduino-uno" else PART_PINS[t]
            assert pin in allowed, end


def test_twin_wiring_matches_sketch_pins() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    wires = {frozenset(c[:2]) for c in d["connections"]}
    for a, b in [
        ("hx711:DT", "uno:3"),
        ("hx711:SCK", "uno:4"),
        ("servo:PWM", "uno:6"),
        ("buzzer:2", "uno:8"),
        ("ntc:OUT", "uno:A0"),
        ("pulse_pot:SIG", "uno:A1"),
    ]:
        assert frozenset((a, b)) in wires, (a, b)
    for line in (
        "PIN_HX_DOUT = 3, PIN_HX_SCK = 4, PIN_SERVO = 6, PIN_BUZZER = 8",
        "PIN_NTC = A0, PIN_PULSE = A1",
    ):
        assert line in SKETCH.read_text()


def test_twin_simulated_parts_are_labelled() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    texts = " ".join(p["attrs"]["text"] for p in d["parts"] if p["type"] == "wokwi-text").lower()
    assert "pulse stand-in (simulated)" in texts
    assert "skin probe stand-in (simulated)" in texts
    assert "load cell (simulated)" in texts


def test_twin_toml_points_at_arduino_cli_output() -> None:
    toml = (TWIN / "wokwi.toml").read_text()
    assert "build/exercise-uno.ino.hex" in toml and "build/exercise-uno.ino.elf" in toml


def test_twin_libraries_cover_sketch_includes() -> None:
    libs = (TWIN / "libraries.txt").read_text()
    assert "HX711" in libs and "Servo" in libs


def test_no_company_name_in_rig_files() -> None:
    for f in [SKETCH, *TWIN.glob("*"), *(FW / "exercise-uno" / "test").glob("*")]:
        if f.is_file():
            assert "vocaid" not in f.read_text(errors="ignore").lower(), f


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
def test_exercise_pure_block_host_tests() -> None:
    aj = [
        Path.home() / "Documents/Arduino/libraries/ArduinoJson/src",
        Path.home() / "Arduino/libraries/ArduinoJson/src",
    ]
    if not any(p.is_dir() for p in aj):
        pytest.skip("ArduinoJson not installed")
    r = subprocess.run(
        [str(FW / "exercise-uno/test/run_host_tests.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("ok")
