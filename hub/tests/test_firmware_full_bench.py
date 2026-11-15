"""Full bench circuit in one Wokwi project (D40): UNO block, tilt-1 block, Pi hub circuit abstraction."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FW = Path(__file__).resolve().parents[2] / "firmware"
BENCH = FW / "wokwi" / "full-bench"
TILT_TWIN = "https://wokwi.com/projects/480680478751478785"

# Pin names from docs.wokwi.com/parts/<type>, read 2026-11-14; chips from their *.chip.json.
PART_PINS = {
    "wokwi-dht22": {"VCC", "SDA", "NC", "GND"},
    "wokwi-buzzer": {"1", "2"},
    "wokwi-slide-switch": {"1", "2", "3"},
    "chip-nimh-pack": {"+", "-"},
    "chip-rpi3-hub": {"RX", "TX", "GND", "PWR_IN", "MICROSD", "HEADER_EMPTY"},
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


def test_pi_hub_reads_the_uno_uart_and_keeps_its_header_empty() -> None:
    spec = json.loads((BENCH / "rpi3-hub.chip.json").read_text())
    assert spec["name"] == "Raspberry Pi 3 Model B hub (circuit abstraction)"
    assert {"RX", "TX", "GND", "HEADER_EMPTY"} <= set(spec["pins"])
    assert [c["id"] for c in spec["controls"]] == ["alert"]
    assert "void chip_init(void)" in (BENCH / "rpi3-hub.chip.c").read_text()
    # The bench's USB serial is drawn as the UNO's UART (the UNO's USB bridge feeds D0/D1): crossed, plus ground.
    wires = {frozenset(c[:2]): c[2] for c in _diagram()["connections"]}
    assert frozenset(("uno:1", "hub:RX")) in wires  # UNO TX → hub RX
    assert frozenset(("hub:TX", "uno:0")) in wires  # hub TX → UNO RX
    assert wires[frozenset(("hub:GND", "uno:GND.3"))] == "black"
    hub_ends = {end for c in _diagram()["connections"] for end in c[:2] if end.startswith("hub:")}
    assert hub_ends == {"hub:RX", "hub:TX", "hub:GND"}  # header, power and microSD stay unwired (D40)
    texts = _texts()
    assert "40-pin header: empty: nothing wired here" in texts
    assert "usb serial 250000 → /dev/ttyacm0" in texts
    assert "wi-fi 2.4 ghz → mqtt :1883 (mosquitto on the pi)" in texts
    assert "micro-usb 5 v 2.5 a" in texts and "microsd" in texts
    assert "circuit abstraction" in texts


def _chip_define(name: str) -> float:
    for line in (BENCH / "rpi3-hub.chip.c").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "#define" and parts[1] == name:
            return float(parts[2])
    raise AssertionError(f"{name} not defined in rpi3-hub.chip.c")


def test_hub_chip_bands_match_the_thresholds_file() -> None:
    rules = {r["id"]: r for r in json.loads((FW.parent / "data" / "thresholds.json").read_text())}
    for rule_id, prefix in (
        ("cabin_health_box_temp", "TEMP_HEALTH"), ("cabin_performance_temp", "TEMP_PERF"),
        ("cabin_health_box_rh", "RH_HEALTH"), ("cabin_performance_rh", "RH_PERF"),
    ):  # fmt: skip
        ok = rules[rule_id]["ok"]
        assert _chip_define(f"{prefix}_MIN") == ok["min"], rule_id
        assert _chip_define(f"{prefix}_MAX") == ok["max"], rule_id
    # health rules fail into act, performance rules into watch, as in the chip
    assert "act" in rules["cabin_health_box_temp"] and "watch" in rules["cabin_performance_temp"]
    assert "act" in rules["cabin_health_box_rh"] and "watch" in rules["cabin_performance_rh"]


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_hub_chip_native_tests() -> None:
    r = subprocess.run(
        [str(BENCH / "test" / "run_chip_tests.sh")], check=False, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hub chip ok" in r.stdout


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
