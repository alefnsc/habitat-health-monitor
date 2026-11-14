"""Vitals node checks that need no board: Wokwi twin sync, diagram and chip sanity, host tests."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FW = Path(__file__).resolve().parents[2] / "firmware"
SKETCH = FW / "vitals-esp32" / "vitals-esp32.ino"
TWIN = FW / "wokwi" / "vitals-esp32"
HOME = Path.home()


def test_twin_sketch_is_byte_identical_to_vitals_sketch() -> None:
    assert (TWIN / "sketch.ino").read_bytes() == SKETCH.read_bytes(), (
        "run firmware/wokwi/vitals-esp32/sync.sh"
    )


def test_sketch_pin_map_and_addresses() -> None:
    text = SKETCH.read_text()
    assert "#if defined(ESP8266)" in text
    assert "PIN_SDA = 4" in text and "PIN_SCL = 5" in text  # D2 and D1
    assert "ADDR_MAX = 0x57, ADDR_MLX = 0x5A, ADDR_MPU = 0x68" in text
    assert "ds18b20" not in text.lower()


def test_twin_diagram_parts_and_wiring() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    parts = {p["id"]: p for p in d["parts"]}
    assert len(parts) == len(d["parts"])
    types = {p["type"] for p in d["parts"]}
    assert types >= {"wokwi-esp32-devkit-v1", "chip-max30102", "chip-mlx90614", "wokwi-mpu6050"}
    chip_pins = {
        "chip-max30102": set(json.loads((TWIN / "max30102.chip.json").read_text())["pins"]),
        "chip-mlx90614": set(json.loads((TWIN / "mlx90614.chip.json").read_text())["pins"]),
        "wokwi-mpu6050": {"VCC", "GND", "SCL", "SDA", "XDA", "XCL", "AD0", "INT"},
    }
    wires = set()
    for a, b, *_ in d["connections"]:
        wires.add(frozenset((a, b)))
        for end in (a, b):
            pid, pin = end.split(":", 1)
            assert pid in parts, end
            if parts[pid]["type"] in chip_pins:
                assert pin in chip_pins[parts[pid]["type"]], end
    for dev in ("max", "mlx", "mpu"):
        for esp_pin, pin in (("D21", "SDA"), ("D22", "SCL"), ("3V3", "VCC"), ("GND.1", "GND")):
            assert frozenset((f"esp:{esp_pin}", f"{dev}:{pin}")) in wires, (dev, pin)


def test_every_simulated_part_is_labelled() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    texts = [p["attrs"]["text"] for p in d["parts"] if p["type"] == "wokwi-text"]
    for needle in ("MAX30102", "MLX90614", "MPU6050", "ESP32 stands in"):
        assert any(needle in t and "simulated" in t for t in texts), needle
    for f in ("max30102.chip.json", "mlx90614.chip.json"):
        assert "simulated" in json.loads((TWIN / f).read_text())["name"]


@pytest.mark.parametrize("name,addr", [("max30102", "0x57"), ("mlx90614", "0x5A")])
def test_chip_files_match_each_other(name: str, addr: str) -> None:
    spec = json.loads((TWIN / f"{name}.chip.json").read_text())
    c = (TWIN / f"{name}.chip.c").read_text()
    assert {"SCL", "SDA", "VCC", "GND"} <= set(spec["pins"])
    assert f".address = {addr}" in c
    for p in ("SCL", "SDA"):
        assert f'pin_init("{p}"' in c
    for ctl in spec["controls"]:  # every control is read as an attribute of the same name
        assert re.search(rf'attr_init(_float)?\("{ctl["id"]}"', c), ctl["id"]
        assert ctl["type"] == "range" and ctl["min"] < ctl["max"]
    assert "chip_init" in c


def test_max30102_chip_part_id() -> None:
    c = (TWIN / "max30102.chip.c").read_text()
    assert "REG_PART_ID 0xFF" in c and "0x15" in c


def test_readme_lists_every_paste_file() -> None:
    readme = (TWIN / "README.md").read_text()
    for f in (
        "sketch.ino",
        "diagram.json",
        "libraries.txt",
        "max30102.chip.json",
        "max30102.chip.c",
        "mlx90614.chip.json",
        "mlx90614.chip.c",
    ):
        assert f in readme and (TWIN / f).is_file(), f


def test_no_company_name_or_ds18b20_left() -> None:
    for f in [SKETCH, *TWIN.rglob("*"), *(FW / "vitals-esp32/test").glob("*")]:
        if f.is_file() and f.suffix in {".ino", ".c", ".cpp", ".h", ".json", ".md", ".sh", ".txt"}:
            low = f.read_text(errors="ignore").lower()
            assert "vocaid" not in low, f
    assert "DS18B20" not in (FW / "vitals-esp32/libraries.txt").read_text()


def _aj() -> bool:
    return any(
        p.is_dir()
        for p in (
            HOME / "Documents/Arduino/libraries/ArduinoJson/src",
            HOME / "Arduino/libraries/ArduinoJson/src",
        )
    )


@pytest.mark.skipif(shutil.which("c++") is None, reason="no C++ compiler")
def test_vitals_pure_block_host_tests() -> None:
    if not _aj():
        pytest.skip("ArduinoJson not installed")
    r = subprocess.run(
        [str(FW / "vitals-esp32/test/run_host_tests.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("ok")


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_wokwi_chips_native_tests() -> None:
    sf = (
        HOME
        / "Documents/Arduino/libraries/SparkFun_MAX3010x_Pulse_and_Proximity_Sensor_Library/src"
    )
    if not sf.is_dir():
        pytest.skip("SparkFun MAX3010x library not installed")
    r = subprocess.run(
        [str(TWIN / "test/run_chip_tests.sh")], check=False, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("ok") >= 2
