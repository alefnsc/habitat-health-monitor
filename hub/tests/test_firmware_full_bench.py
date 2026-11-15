"""Full bench circuit in one Wokwi project (D40): UNO block, tilt-1 block, Pi hub drawing."""

from __future__ import annotations

import json
from pathlib import Path

FW = Path(__file__).resolve().parents[2] / "firmware"
BENCH = FW / "wokwi" / "full-bench"
TILT_TWIN = "https://wokwi.com/projects/480680478751478785"

# Pin names from docs.wokwi.com/parts/<type>, read 2026-11-14; chips from their *.chip.json.
PART_PINS = {
    "wokwi-dht22": {"VCC", "SDA", "NC", "GND"},
    "wokwi-buzzer": {"1", "2"},
    "wokwi-slide-switch": {"1", "2", "3"},
    "chip-nimh-pack": {"+", "-"},
    "chip-rpi3-hub": {"USB_A", "PWR_IN", "MICROSD", "HEADER_EMPTY"},
}
UNO_PINS = {"5V", "GND.1", "GND.2", "GND.3", "A0", "A1"} | {str(i) for i in range(14)}
ESP_PINS = {"3V3", "VIN", "GND.1", "GND.2"} | {
    f"D{i}" for i in (2, 4, 5, 12, 13, 14, 15, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 34, 35)
}


def _diagram() -> dict:
    return json.loads((BENCH / "diagram.json").read_text())


def _texts() -> str:
    return " ".join(
        p["attrs"]["text"] for p in _diagram()["parts"] if p["type"] == "wokwi-text"
    ).lower()


def test_copies_equal_their_sources() -> None:
    pairs = [
        (FW / "exercise-uno" / "exercise-uno.ino", BENCH / "sketch.ino"),
        (FW / "wokwi" / "uno-rig" / "wokwi_twin.h", BENCH / "wokwi_twin.h"),
        (FW / "wokwi" / "tilt-esp32" / "nimh-pack.chip.json", BENCH / "nimh-pack.chip.json"),
        (FW / "wokwi" / "tilt-esp32" / "nimh-pack.chip.c", BENCH / "nimh-pack.chip.c"),
    ]
    for src, copy in pairs:
        assert copy.read_bytes() == src.read_bytes(), (
            f"run firmware/wokwi/full-bench/sync.sh ({copy.name})"
        )


def test_parts_and_pins_are_valid() -> None:
    d = _diagram()
    parts = {p["id"]: p for p in d["parts"]}
    assert len(parts) == len(d["parts"]), "duplicate part ids"
    for a, b, *_ in d["connections"]:
        for end in (a, b):
            pid, pin = end.split(":", 1)
            assert pid in parts, end
            t = parts[pid]["type"]
            allowed = (
                UNO_PINS if t == "wokwi-arduino-uno"
                else ESP_PINS if t == "wokwi-esp32-devkit-v1"
                else PART_PINS[t]
            )  # fmt: skip
            assert pin in allowed, end


def test_uno_is_the_first_mcu_so_it_runs_the_sketch() -> None:
    mcus = [
        p["id"]
        for p in _diagram()["parts"]
        if p["type"].startswith(("wokwi-arduino", "wokwi-esp32"))
    ]
    assert mcus == ["uno", "esp"]


def test_uno_block_wiring_and_colours() -> None:
    wires = {frozenset(c[:2]): c[2] for c in _diagram()["connections"]}
    assert wires[frozenset(("dht:SDA", "uno:2"))] == "green"
    assert wires[frozenset(("dht:VCC", "uno:5V"))] == "red"
    assert wires[frozenset(("dht:GND", "uno:GND.1"))] == "black"
    assert wires[frozenset(("buzzer:2", "uno:8"))] == "purple"
    assert wires[frozenset(("buzzer:1", "uno:GND.2"))] == "black"


def test_tilt_block_wiring_matches_the_tilt_twin() -> None:
    wires = {frozenset(c[:2]): c[2] for c in _diagram()["connections"]}
    assert wires[frozenset(("tilt_sw:1", "esp:3V3"))] == "red"
    assert wires[frozenset(("tilt_sw:2", "esp:D14"))] == "yellow"
    assert wires[frozenset(("tilt_sw:3", "esp:GND.1"))] == "black"
    assert wires[frozenset(("pack:+", "esp:VIN"))] == "red"
    assert wires[frozenset(("pack:-", "esp:GND.2"))] == "black"


def test_pi_hub_is_a_drawing_with_an_empty_header() -> None:
    spec = json.loads((BENCH / "rpi3-hub.chip.json").read_text())
    assert spec["name"] == "Raspberry Pi 3 Model B hub (drawing only)"
    assert "HEADER_EMPTY" in spec["pins"]
    assert "void chip_init(void)" in (BENCH / "rpi3-hub.chip.c").read_text()
    # nothing is wired to the Pi in the diagram, least of all its header (D40)
    assert not any("hub:" in end for c in _diagram()["connections"] for end in c[:2])
    texts = _texts()
    assert "40-pin header: empty: nothing wired here" in texts
    assert "usb serial 250000 → /dev/ttyacm0" in texts
    assert "wi-fi 2.4 ghz → mqtt :1883 (mosquitto on the pi)" in texts
    assert "micro-usb 5 v 2.5 a" in texts and "microsd" in texts


def test_panel_flow_rules_and_labels() -> None:
    texts = _texts()
    for phrase in (
        "nasa-std-3001",
        "simulated mars link",
        "earth page",
        "nothing on the pi header",
        "never the cell pack and usb at once",
        "adults only",
        "simulated parts are labelled",
        "not a medical device",
        "dht11 stand-in (simulated)",
        "ky-017 stand-in (simulated)",
        "esp32 stands in for the nodemcu",
        TILT_TWIN,
    ):
        assert phrase in texts, phrase
    for f in BENCH.rglob("*"):
        if f.is_file():
            assert "vocaid" not in f.read_text(errors="ignore").lower(), f


def test_readme_lists_paste_files_and_link() -> None:
    readme = (BENCH / "README.md").read_text()
    for f in (
        "sketch.ino", "wokwi_twin.h", "diagram.json", "libraries.txt",
        "nimh-pack.chip.json", "nimh-pack.chip.c", "rpi3-hub.chip.json", "rpi3-hub.chip.c",
    ):  # fmt: skip
        assert f in readme and (BENCH / f).is_file(), f
    assert "https://wokwi.com/projects/" in readme
