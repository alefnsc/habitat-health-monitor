# Fewer processors: two MCUs and a hub — design (D40)

Status: approved by the team owner, 2026-11-14 ~14:05, after a bench re-check and a six-agent review. The review
compared three layouts: Pi only; Pi plus NodeMCU; Pi hub plus the UNO as the one I/O board. This design is the third,
with the tilt node from D39 kept on its own battery.

## 1. Goal

Run the habitat on as few boards as the demo allows, with a simple circuit a judge can read from one diagram. Keep a
Wokwi simulation of every board that runs our firmware, and keep every contract-v1 reading that the parts on the bench
can really make.

## 2. Layout

| Board | Runs | Wired to it | Link | Power |
|---|---|---|---|---|
| Raspberry Pi 3 Model B | hub, Mosquitto, console | nothing on the 40-pin header | n/a | 5 V 2.5 A supply; a laptop runs the hub instead if the Pi is not ready |
| UNO+WiFi R3, ATmega328P side | `firmware/exercise-uno` | DHT11 on D2, buzzer on D8 | USB serial to the hub, 250000 baud | USB from the hub |
| UNO+WiFi R3, ESP8266 side | nothing | — | — | DIP switch set to "USB to ATmega328" |
| NodeMCU (ESP8266) | `firmware/tilt-esp8266` (D39) | KY-017 tilt pod on D5 | Wi-Fi/MQTT to the hub's broker | 4 × Ni-MH AA on VIN and GND (or 2 × alkaline AA/AAA on 3V3) |

There are two microcontrollers (the ATmega and the NodeMCU's ESP8266) and one hub computer. Before D40 there were four
or five processors: the Pi, the ATmega, the UNO's ESP8266 as a bridge, the NodeMCU as the tilt node, and a D1 mini to
buy as the vitals node.

## 3. What each board reports

| Node | Board | Readings |
|---|---|---|
| `cabin-1` | UNO (serial) | `cabin_temp` (C), `cabin_rh` (%), dev `DHT11`, src `hobby`, every 5 s |
| `exercise-1` | UNO (serial) | command acks; `load_raw`, `skin_temp`, `hr` only when their build flags are on (all off by default) |
| `tilt-1` | NodeMCU (MQTT) | `tilt` (state), dev `KY017`, as in D39 §4 |

`cabin_p` and `cabin_co2` stay in the contract. They come back if a BME280 or SCD41 is ever wired, and until then
they are shown only from replay files. Wearable vitals (`hr`, `spo2`, `sleep_h`) will come from the team owner's own
ring through an importer. That importer is the next step (§9) and is not part of this design.

## 4. UNO firmware (`firmware/exercise-uno/exercise-uno.ino`)

- **Build flags**, defaults in bold:
  - `ENABLE_DHT` **1**;
  - `ENABLE_HX711` **0**, `ENABLE_SERVO` **0**, `ENABLE_NTC` **0**, `ENABLE_KY039` **0**;
  - `BUZZER_PASSIVE` **1** (the bench buzzer is passive: it only clicked on a steady HIGH and beeped with tone(), checked 14/11);
  - `DHT_TYPE` **DHT11**.

  A module that is not wired is compiled out, so no floating pin ever publishes numbers. A floating HX711 DOUT pin
  would read as "ready" and stream noise.
- **Twin overrides.** The sketch includes `wokwi_twin.h` only when that file exists next to it
  (`__has_include`, the same pattern as `secrets.h` in the ESP sketches). The real sketch folder has no such file.
  The Wokwi project has it, and it sets `DHT_TYPE DHT22` and `BUZZER_PASSIVE 1`, because Wokwi has no DHT11 and its
  buzzer is a passive piezo. So the twin's `sketch.ino` stays byte-identical to the real one.
- **DHT11** on D2, read every 5 s through the Adafruit DHT library (already pinned, `DHT sensor library@1.4.7`):
  - `cabin_temp` and `cabin_rh` with node `cabin-1`;
  - `out_of_range` outside the DHT11 ranges, 0–50 °C and 20–90 %RH;
  - after 3 failed reads in a row, val 0 with `no_contact`, as `nodes/cabin_pi` does.

  The flag rules are pure functions with host tests.
- **Node per line.** `buildReading` takes the node name. Acks stay on `exercise-1`.
- **Buzzer** on D8, unchanged alarm pattern (500 ms on, 500 ms off): `digitalWrite` for an active module, or
  `tone(2000 Hz)` / `noTone` for a passive one, called only when the state changes.
- **Commands.** `servo`, `cal` and `tare` answer `ok:false, err:"not_built"` when their part is compiled out.
  `alarm` always works.
- **Unchanged:** 250000 baud, the EEPROM boot counter, and the `# exercise-1 boot=` banner. The banner gains a
  `# channels` line listing every flag.

## 5. Hub

- `hub/serial_rig.py` ingests readings whose node is in `SERIAL_NODES = {"exercise-1", "cabin-1"}`. Any other node on
  the serial line is still rejected with `topic_node_mismatch`. Connecting and disconnecting the port marks both nodes
  online or offline together. Commands still go to `exercise-1`.
- `Ingestor.ingest_reading(expected_node=...)` accepts one node name or a collection of them.
- No contract change: `cabin-1`, `DHT11`, `tilt-1` and `KY017` are already in `hub/contract.py`.

## 6. Tilt node (D39, amended)

- **Power.** Firmware, pins and contract are as in D39. The pod rides on the weight with no cable, on one of two packs.
  The first is the operator's choice, made 2026-11-14 ~15:00 after the bench showed the team's AA cells are 1.2 V Ni-MH.
  - **Chosen: 4 × Ni-MH AA in series** (about 4.8–5.6 V) into **VIN** and **GND**. The board's regulator makes 3.3 V.
    With 2,450 mAh cells and Wi-Fi on all the time (about 80 mA), it lasts roughly a day.
  - **Alternative: 2 × alkaline AA or AAA in series** (3.0–3.2 V fresh) on **3V3** and **GND**, about 15 hours.
- **Pack rules:**
  - Never 2 cells on VIN: the regulator needs more than about 4.5 V. Two Ni-MH on 3V3 are too low as well (2.4–2.8 V).
  - Never 3 or more cells on 3V3: more than 3.6 V destroys the board.
  - Never mix cell types or charge levels in one pack.
  - The KY-017 stays on 3V3 and GND, never on VIN.
  - A CR2032 coin cell cannot supply the Wi-Fi bursts (170–300 mA) and is not used.
  - Unplug the pack before plugging USB in to flash.
- **What it replaces.** This replaces "USB power from the hub" in D39 §3. It also removes the case of a held weight
  cabled to a mains-powered board.
- **Superseded.** D39 §7 (vitals node on a Wemos D1 mini) is superseded: there is no vitals board.

## 7. Wokwi twins (both edited in place, so the shared links do not change)

| Link (unchanged) | Before | After |
|---|---|---|
| https://wokwi.com/projects/480675272836723713 | exercise rig: HX711, servo, buzzer, NTC, pulse potentiometer | UNO I/O board: the real `exercise-uno` sketch, `wokwi_twin.h`, a `wokwi-dht22` labelled "DHT11 stand-in (simulated)" on D2, `wokwi-buzzer` on D8 |
| https://wokwi.com/projects/480680478751478785 | vitals node (ESP32 stand-in, MAX30102/MLX90614 chips, MPU6050) | tilt-1 node: the real `tilt-esp8266` sketch in serial-only mode on an ESP32 stand-in, a `wokwi-slide-switch` labelled "KY-017 stand-in (simulated)" on GPIO14 |

- **Repo copies.** `firmware/wokwi/uno-rig/` is updated. `firmware/wokwi/tilt-esp32/` is new, with a byte-parity
  check against `firmware/tilt-esp8266/tilt-esp8266.ino`.
- **Archived.** `firmware/wokwi/vitals-esp32/` and `firmware/vitals-esp32/` stay in the tree as archived design
  history, with their tests, and say so at the top.

## 8. Docs

- `README.md`: hardware layout.
- `firmware/README.md`: board table and commands.
- `docs/pi-setup.md`: the Pi is the hub only, and `HUB_SERIAL_PORT` points at the UNO.
- `scripts/pi-setup.sh`: `habitat-cabin` is installed but no longer enabled, because nothing is on the Pi's header and
  `cabin-1` now comes from the UNO.
- `docs/safety-checklist.md`: the tilt node runs on cells, and the battery rules above.
- `docs/decisions/links.md`: the twins' new contents.
- `firmware/tilt-esp8266/README.md`: battery power.
- The F19 wiring diagrams follow §2: one UNO page and one NodeMCU page.

## 9. Out of scope

- The ring importer (OAuth, `ring-1`, dev `RING`). It is the next step.
- A BME280 or SCD41 on the UNO's I2C pins.
- Using the UNO's ESP8266 as a Wi-Fi bridge.
- Removing the archived sketches.

## 10. Testing

- `pytest -q` for the full suite. New tests:
  - `cabin-1` lines are accepted over serial;
  - any other node is still rejected;
  - both nodes go online and offline together;
  - the twin parity, diagram and label checks for both twins.
- Host tests for the UNO's pure block: DHT11 flags, the fail counter, and the node in the line.
- Host tests for the tilt node (D39, unchanged).
- `arduino-cli compile` for:
  - `arduino:avr:uno` with the default flags and with every flag on;
  - `esp8266:esp8266:nodemcuv2` and `esp32:esp32:esp32` for the tilt sketch.
- A Wokwi run of each twin after it is saved: the serial monitor shows the banner and contract-v1 lines.
