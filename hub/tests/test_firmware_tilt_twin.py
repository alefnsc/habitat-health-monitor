"""tilt-1 Wokwi twin (D40): an ESP32 stand-in running the real tilt sketch in serial-only mode."""

from __future__ import annotations

import json
from pathlib import Path

FW = Path(__file__).resolve().parents[2] / "firmware"
SKETCH = FW / "tilt-esp8266" / "tilt-esp8266.ino"
TWIN = FW / "wokwi" / "tilt-esp32"

# Pin names from docs.wokwi.com/parts/<type>, read 2026-11-14.
PART_PINS = {"wokwi-slide-switch": {"1", "2", "3"}}
ESP_PINS = {"3V3", "VIN", "GND.1", "GND.2"} | {
    f"D{i}" for i in (2, 4, 5, 12, 13, 14, 15, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 34, 35)
}


def test_twin_sketch_is_byte_identical_to_tilt_sketch() -> None:
    assert (TWIN / "sketch.ino").read_bytes() == SKETCH.read_bytes(), (
        "run firmware/wokwi/tilt-esp32/sync.sh"
    )


def test_diagram_wiring_and_labels() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    parts = {p["id"]: p for p in d["parts"]}
    assert len(parts) == len(d["parts"]), "duplicate part ids"
    assert parts["esp"]["type"] == "wokwi-esp32-devkit-v1"
    assert parts["tilt_sw"]["type"] == "wokwi-slide-switch"
    for a, b, *_ in d["connections"]:
        for end in (a, b):
            pid, pin = end.split(":", 1)
            assert pid in parts, end
            allowed = ESP_PINS if pid == "esp" else PART_PINS[parts[pid]["type"]]
            assert pin in allowed, end
    wires = {frozenset(c[:2]) for c in d["connections"]}
    assert frozenset(("tilt_sw:2", "esp:D14")) in wires  # PIN_TILT = 14 (D5 on the NodeMCU)
    # default position is left (pins 1-2): released, tilt 0; slide right (pins 2-3) to GND: tilt 1
    assert frozenset(("tilt_sw:3", "esp:GND.1")) in wires
    assert not any("tilt_sw:1" in c[:2] for c in d["connections"])
    assert "PIN_TILT = 14" in SKETCH.read_text()


def test_simulated_parts_are_labelled() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    texts = " ".join(p["attrs"]["text"] for p in d["parts"] if p["type"] == "wokwi-text").lower()
    assert "ky-017 stand-in (simulated)" in texts
    assert "esp32 stands in for the nodemcu" in texts
    assert "not a medical device" in texts


def test_readme_paste_files_link_and_battery_rule() -> None:
    readme = (TWIN / "README.md").read_text()
    for f in ("sketch.ino", "diagram.json", "libraries.txt"):
        assert f in readme and (TWIN / f).is_file(), f
    assert "480680478751478785" in readme
    tilt = (FW / "tilt-esp8266" / "README.md").read_text().lower()
    for rule in (
        "4 × ni-mh aa",
        "vin",
        "3v3",
        "never 2 cells on vin",
        "never 3 or more cells on 3v3",
        "cr2032",
    ):
        assert rule in tilt, rule
    assert "power over usb from the hub" not in tilt  # D40: the pod rides on cells
    for f in TWIN.rglob("*"):
        if f.is_file():
            assert "vocaid" not in f.read_text(errors="ignore").lower(), f


def test_vitals_twin_marked_archived() -> None:
    readme = (FW / "wokwi" / "vitals-esp32" / "README.md").read_text().lower()
    assert "archived (d40)" in readme and "tilt-esp32" in readme
