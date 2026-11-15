# Wokwi: the full bench circuit in one project (decision D40)

Educational prototype, not a medical device. This is a simulation, and every part below is simulated or drawn, and
labelled so on the canvas.

**Saved project (share link):** https://wokwi.com/projects/480768002795017217, "Habitat Health Monitor – full bench
circuit (Space Apps 2026)". Saved 2026-11-15. After a reload, the eight stored files matched this folder byte for byte
(SHA-256).

The two twins stay as they are:
- the UNO I/O board: https://wokwi.com/projects/480675272836723713 (`../uno-rig`);
- the tilt-1 node: https://wokwi.com/projects/480680478751478785 (`../tilt-esp32`).

## What is on the canvas

| Block | Parts | Runs here? |
|---|---|---|
| UNO I/O board | `wokwi-arduino-uno` running `sketch.ino` (= `firmware/exercise-uno`) with `wokwi_twin.h`; `wokwi-dht22` as the DHT11 stand-in on D2; `wokwi-buzzer` on D8 | **Yes**: the banner, then `cabin-1` lines every 5 s |
| tilt-1 node | `wokwi-esp32-devkit-v1` standing in for the NodeMCU; `wokwi-slide-switch` as the 3-wire KY-017 stand-in (1 → 3V3, 2 → D14 = D5, 3 → GND); the `nimh-pack` drawing chip on VIN/GND | **No**: drawn, and it runs in its own twin (link above) |
| Hub | `chip-rpi3-hub`, "Raspberry Pi 3 Model B hub (circuit abstraction)": `RX`, `TX`, `GND` wired to the UNO's UART; `PWR_IN`, `MICROSD`, `HEADER_EMPTY` drawn and unwired; an `alert` control | **Its UNO-link job, yes** (see below). Wokwi has no Raspberry Pi 3 (it runs Linux) |

The canvas wires use one colour per signal: red 5V/3V3/VIN, black GND, green D2, purple D8, and yellow for the tilt
signal. Text on the canvas gives:
- the links that are not wires: "USB serial 250000 → /dev/ttyACM0" between the UNO and the Pi, and "Wi-Fi 2.4 GHz →
  MQTT :1883 (Mosquitto on the Pi)" between the tilt node and the Pi;
- the data flow: UNO → serial → hub → NASA-STD-3001 rules → console; tilt-1 → Wi-Fi → MQTT → hub; hub → simulated
  Mars link → Earth page;
- the bench rules: nothing on the Pi header; never the cell pack and USB at once; mercury pod sealed, adults only.

## Why the ESP32 does not run here

Wokwi runs one microcontroller per project. Its FAQ answers "How do I use multiple microcontrollers in a single
project?" with "currently unsupported". It was also tested in this project on 2026-11-15, with the UNO first and the
ESP32 second in the diagram:
- only the UNO's output appeared (`# exercise-1 boot=1`, the `# channels` line, `cabin-1` lines);
- the ESP32 printed none of its ROM boot lines (`ets …`, `entry 0x…`), which its own twin does print;
- sliding the switch wired to the ESP32 produced nothing.

A second `.ino` file cannot share the project either: the Arduino build merges every `.ino` in the folder into one
program. So the tilt sketch is not copied here; the ESP32 block is a labelled drawing of the real wiring.

## Files to paste (and their sources)

| File in the Wokwi project | Source (kept equal by `./sync.sh`, checked by `./check_sync.sh`) |
|---|---|
| `sketch.ino` | `firmware/exercise-uno/exercise-uno.ino` |
| `wokwi_twin.h` | `firmware/wokwi/uno-rig/wokwi_twin.h` |
| `nimh-pack.chip.json`, `nimh-pack.chip.c` | `firmware/wokwi/tilt-esp32/` |
| `rpi3-hub.chip.json`, `rpi3-hub.chip.c` | this folder (the hub circuit abstraction below) |
| `diagram.json`, `libraries.txt` | this folder |

`hub/tests/test_firmware_full_bench.py` checks the copies, the pins and wire colours, that the UNO is the first
microcontroller (so it is the one that runs), that only the Pi's UART pins are wired, that the chip's cabin bands
equal `data/thresholds.json`, and the canvas text. It also runs `test/run_chip_tests.sh`: native C tests of the hub
chip against a host stand-in for `wokwi-api.h` (`test/stub/`). They do not prove the chip builds on wokwi.com; that
is checked by hand in the saved project.

## The Pi hub as a circuit abstraction

Wokwi cannot run a Raspberry Pi 3, so the `rpi3-hub` custom chip stands in for the one part of the hub's job that
lives on the UNO link:

- **Wiring.** The bench's USB cable is drawn as the UNO's UART, because the UNO's USB bridge feeds D0/D1:
  UNO TX (D1) → hub RX (blue), hub TX → UNO RX (D0) (orange), and ground (black), at 250000 baud. The 40-pin header,
  power and microSD pins are drawn only and stay unwired (D40: nothing on the Pi header).
- **Ingest.** The chip reads the UNO's contract-v1 lines and logs one line per reading in the simulation console,
  for example `hub: cabin-1 cabin_temp 24.0 C -> within the limit (NASA-STD-3001)`. It judges cabin temperature and
  humidity like the hub: worst of the health box (outside it: "outside the limit") and the performance zone (outside
  it: "watch"). A flagged reading is not judged. It also counts banners, acks and rejected lines.
- **Commands.** Its `alert` control stands in for a space-weather (DONKI) act and sends the same command as the
  hub's actuator, `{"v":1,"cmd":"alarm","on":true}`. The UNO acks it and the buzzer pulses; moving the control back
  sends `"on":false`. A cabin breach does **not** sound the buzzer, because the real hub does not do that either.
- **Not here.** Mosquitto, storage, the console, the tilt-1 Wi-Fi link and the simulated Mars link run on the real Pi.

To try it: start the simulation, watch the `hub:` lines in the console, set the DHT22 above 27 °C to see "outside
the limit", then move the hub chip's alert control to 1 and back to hear the buzzer and see the acks.
