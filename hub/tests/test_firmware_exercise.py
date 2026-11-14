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
    "wokwi-dht22": {"VCC", "SDA", "NC", "GND"},
    "wokwi-buzzer": {"1", "2"},
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
    assert {p["type"] for p in d["parts"]} == {"wokwi-arduino-uno", *PART_PINS, "wokwi-text"}
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
    for a, b in [("dht:SDA", "uno:2"), ("buzzer:2", "uno:8")]:
        assert frozenset((a, b)) in wires, (a, b)
    # one colour per signal on the canvas: red 5V, black GND, green D2, purple D8
    colour = {
        "5V": "red",
        "GND.1": "black",
        "GND.2": "black",
        "GND.3": "black",
        "2": "green",
        "8": "purple",
    }
    for a, b, c, *_ in d["connections"]:
        uno_pin = next(e.split(":", 1)[1] for e in (a, b) if e.startswith("uno:"))
        assert c == colour[uno_pin], (a, b, c)
    assert "PIN_DHT = 2," in SKETCH.read_text() and "PIN_BUZZER = 8;" in SKETCH.read_text()


def test_twin_simulated_parts_are_labelled() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    texts = " ".join(p["attrs"]["text"] for p in d["parts"] if p["type"] == "wokwi-text").lower()
    assert "dht11 stand-in (simulated)" in texts
    # the bench wiring map for the real board (D40, plain UNO R3 or the UNO+WiFi's ATmega side)
    assert "real bench wiring (arduino uno r3, or the uno+wifi's atmega side)" in texts
    assert "dht11 module: s → d2, + → 5v, − → gnd" in texts
    assert "buzzer module: s → d8, − → gnd" in texts and "only if it is printed + or vcc" in texts
    assert "match each pin by its printed letter, not by its position" in texts
    assert "not a medical device" in texts
    # D40: the load cell and pulse module are not on the board
    assert "load cell" not in texts and "pulse" not in texts


def test_twin_header_sets_stand_ins_and_bench_has_none() -> None:
    h = (TWIN / "wokwi_twin.h").read_text()
    assert "#define DHT_TYPE DHT22" in h and "#define BUZZER_PASSIVE 1" in h
    assert '__has_include("wokwi_twin.h")' in SKETCH.read_text()
    assert not (SKETCH.parent / "wokwi_twin.h").exists()  # the bench build keeps DHT11 + active


def test_sketch_defaults_match_d40() -> None:
    text = SKETCH.read_text()
    for flag, val in [
        ("ENABLE_DHT", 1), ("ENABLE_HX711", 0), ("ENABLE_SERVO", 0),
        ("ENABLE_NTC", 0), ("ENABLE_KY039", 0), ("BUZZER_PASSIVE", 0),
    ]:  # fmt: skip
        assert f"#ifndef {flag}\n#define {flag} {val}\n#endif" in text, flag
    assert "#define DHT_TYPE DHT11" in text
    assert 'NODE_CABIN[] = "cabin-1"' in text


def test_twin_toml_points_at_arduino_cli_output() -> None:
    toml = (TWIN / "wokwi.toml").read_text()
    assert "build/exercise-uno.ino.hex" in toml and "build/exercise-uno.ino.elf" in toml


def test_twin_libraries_cover_sketch_includes() -> None:
    libs = (TWIN / "libraries.txt").read_text()
    assert "DHT sensor library@1.4.7" in libs
    assert "HX711" not in libs and "Servo" not in libs  # compiled out in the D40 defaults


def test_readme_lists_every_paste_file() -> None:
    readme = (TWIN / "README.md").read_text()
    for f in ("sketch.ino", "wokwi_twin.h", "diagram.json", "libraries.txt"):
        assert f in readme and (TWIN / f).is_file(), f
    assert "480675272836723713" in readme


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
