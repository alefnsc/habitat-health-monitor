# Wokwi twin of the tilt-1 node (ESP32 stand-in, decisions D39 and D40)

Educational prototype, not a medical device. This is a simulation, and every part below is simulated and labelled so in
the diagram.
- **The board:** Wokwi has no ESP8266, so an ESP32 stands in for the NodeMCU. It runs the real
  `firmware/tilt-esp8266/tilt-esp8266.ino` unchanged.
- **The mode:** the twin has no `secrets.h`, so the sketch runs in serial-only mode and prints the same contract-v1 lines
  that the real node publishes over MQTT.

| Simulated part | Stands in for | Pin |
|---|---|---|
| `wokwi-esp32-devkit-v1`, labelled "ESP32 stands in for the NodeMCU" | NodeMCU (ESP8266) | — |
| `wokwi-slide-switch`, labelled "KY-017 stand-in (simulated)" | sealed KY-017 mercury tilt pod (`tilt`, dev `KY017`) | common (2) to GPIO14 (D5 on the NodeMCU), pin 3 to GND |

The switch starts in the left position, where pins 1 and 2 are joined. Pin 1 is not connected, so the input pull-up
reads high and `tilt` is 0, the weight at rest. Slide it right to join pins 2 and 3: GPIO14 goes to GND and `tilt` is 1,
the weight tilted past the trip angle. Part and pin names follow docs.wokwi.com/parts/ (read 2026-11-14).

**Saved project (share link):** https://wokwi.com/projects/480680478751478785. Until D40 this link held the vitals node
twin (`../vitals-esp32`, now archived); the tilt-1 twin replaced it in place.

## What runs where (also written on the Wokwi canvas)

- **Code:** the same sketch as the real node. `hub/tests/test_firmware_tilt_twin.py` checks the copy byte for byte.
- **Real node:**
  - a NodeMCU on 2 × AA/AAA cells, on the weight;
  - Wi-Fi/MQTT to the hub's broker;
  - one reading on every debounced change (30 ms) and a heartbeat every 10 s.
- **Twin:** the same lines, on the serial monitor.

## Open it on wokwi.com

1. Open the saved project, or start a new **ESP32** project.
2. Paste these files over the project's files:
   - `firmware/wokwi/tilt-esp32/sketch.ino` into `sketch.ino`;
   - `firmware/wokwi/tilt-esp32/diagram.json` into `diagram.json`;
   - `firmware/wokwi/tilt-esp32/libraries.txt` into `libraries.txt`.

   Delete any other tabs, such as the old `*.chip.c` and `*.chip.json` files.
3. Press Start. The serial monitor shows `# tilt-1 serial-only mode (no secrets.h)`, then a `tilt` line with `"val":0`.
4. Slide the switch right: a line with `"val":1` appears. Slide it back: `"val":0` again.
5. Leave it alone: the same value repeats every 10 s (the heartbeat).

## Keep the copy in sync

`sketch.ino` must be byte-for-byte `firmware/tilt-esp8266/tilt-esp8266.ino`.
- `./sync.sh` refreshes the copy, and `./check_sync.sh` fails when they differ.
- `pytest hub/tests/test_firmware_tilt_twin.py` also fails when they differ.

Build check for the stand-in board: `arduino-cli compile --fqbn esp32:esp32:esp32 firmware/tilt-esp8266`.
