"""tilt-1 Wokwi twin (D40): an ESP32 stand-in running the real tilt sketch in serial-only mode."""

from __future__ import annotations

import json
from pathlib import Path

FW = Path(__file__).resolve().parents[2] / "firmware"
SKETCH = FW / "tilt-esp8266" / "tilt-esp8266.ino"
TWIN = FW / "wokwi" / "tilt-esp32"

# Pin names from docs.wokwi.com/parts/<type>, read 2026-11-14.
PART_PINS = {
    "wokwi-slide-switch": {"1", "2", "3"},
    "chip-nimh-pack": {"+", "-"},  # drawing-only custom chip (nimh-pack.chip.json)
}
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
    wires = {frozenset(c[:2]): c[2] for c in d["connections"]}
    # 3-wire KY-017 stand-in: pin 1 = + (3V3), middle = S (GPIO14 = D5), pin 3 = - (GND).
    # Left (pins 1-2, the default) holds S high: at rest, tilt 0. Right (pins 2-3) pulls S low: tilt 1.
    assert wires[frozenset(("tilt_sw:1", "esp:3V3"))] == "red"
    assert wires[frozenset(("tilt_sw:2", "esp:D14"))] == "yellow"  # PIN_TILT = 14
    assert wires[frozenset(("tilt_sw:3", "esp:GND.1"))] == "black"
    # the 4 x AA Ni-MH pack feeds VIN (D40 amendment), drawn as a do-nothing custom chip
    assert parts["pack"]["type"] == "chip-nimh-pack"
    assert wires[frozenset(("pack:+", "esp:VIN"))] == "red"
    assert wires[frozenset(("pack:-", "esp:GND.2"))] == "black"
    assert (
        "PIN_TILT = 14" in SKETCH.read_text() and "#define TILT_ACTIVE_LOW 1" in SKETCH.read_text()
    )


def test_pack_chip_is_drawing_only() -> None:
    spec = json.loads((TWIN / "nimh-pack.chip.json").read_text())
    assert spec["pins"] == ["+", "-"]
    assert "drawing only" in spec["name"].lower() and "4.8" in spec["name"]
    c = (TWIN / "nimh-pack.chip.c").read_text()
    assert "void chip_init(void)" in c and "pin_init" not in c  # drives nothing


def test_simulated_parts_are_labelled() -> None:
    d = json.loads((TWIN / "diagram.json").read_text())
    texts = " ".join(p["attrs"]["text"] for p in d["parts"] if p["type"] == "wokwi-text").lower()
    assert "ky-017 stand-in (simulated)" in texts
    assert (
        "pin 1 = + (3v3)" in texts
        and "middle = s (d5 / gpio14)" in texts
        and "pin 3 = − (gnd)" in texts
    )
    assert "esp32 stands in for the nodemcu" in texts
    assert "not a medical device" in texts


def test_readme_paste_files_link_and_battery_rule() -> None:
    readme = (TWIN / "README.md").read_text()
    for f in (
        "sketch.ino",
        "diagram.json",
        "libraries.txt",
        "nimh-pack.chip.json",
        "nimh-pack.chip.c",
    ):
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
