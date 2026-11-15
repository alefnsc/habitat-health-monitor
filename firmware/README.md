# Firmware toolchain

Educational prototype, not a medical device. Four sketches, one shared library, exact versions below.

## Which hardware runs what (decision D40, amends D35-D37 and D39) [confirm: hardware member to review before submission]

Two microcontrollers and a hub computer.

| Board | Runs | Wired to it | Link |
|---|---|---|---|
| Raspberry Pi 3 Model B (or a laptop) | hub, Mosquitto, console | nothing on the header | see `docs/pi-setup.md` |
| Arduino UNO R3 (the bench board), or the ATmega328P side of an UNO+WiFi R3 | `exercise-uno` (`arduino:avr:uno`, the same build for both) | DHT11 on D2 (`cabin-1`: `cabin_temp`, `cabin_rh`, hobby estimates), buzzer on D8 (`alarm`) | USB serial to the hub, 250000 baud |
| UNO+WiFi R3 only: its ESP8266 side | nothing (DIP switch: "USB to ATmega328"; see below) | — | — |
| NodeMCU (ESP8266) on 4 × Ni-MH AA (VIN) | `tilt-esp8266` (D39) | sealed KY-017 tilt pod on D5 (`tilt-1`: `tilt`) | Wi-Fi/MQTT |
| Wokwi | two twins, because Wokwi has no ESP8266: the UNO I/O board (`firmware/wokwi/uno-rig/`) and the tilt-1 node on an ESP32 stand-in (`firmware/wokwi/tilt-esp32/`) | — | — |

**`exercise-uno` build flags** (D40 defaults: only what is wired):
- `ENABLE_DHT=1`;
- `ENABLE_HX711=0`, `ENABLE_SERVO=0`, `ENABLE_NTC=0`, `ENABLE_KY039=0`;
- `BUZZER_PASSIVE=1` (the bench buzzer is passive; 0 for an active buzzer);
- `DHT_TYPE=DHT11`.

Turn a channel on only when its module is wired. A floating HX711 DOUT reads as "ready" and would stream noise.

**Commands:** `servo`, `cal` and `tare` answer `ok:false, err:"not_built"` while their part is compiled out. `alarm` always works.

**Tilt node power:** 4 × Ni-MH AA in series on **VIN** and **GND** (chosen), or 2 × alkaline AA/AAA on **3V3** and **GND**.
Never 2 cells on VIN, never 3 or more cells on 3V3, never mix cells in one pack, and no CR2032 coin cell, because it
cannot supply the Wi-Fi bursts. The KY-017 stays on 3V3. See `firmware/tilt-esp8266/README.md`.

**Archived** (kept as design history, with their tests):
- `firmware/vitals-esp32` and `firmware/wokwi/vitals-esp32`: wearable vitals now come from a ring import;
- `firmware/cabin-esp8266`: the empty skeleton.

### Vitals node (D37, archived in D40)

One 3.3 V I2C bus at 100 kHz (the MLX90614's SMBus limit; the plan's 400 kHz would not work with it):
- ESP8266 (Wemos D1 mini, same GPIO4/GPIO5): SDA D2 (GPIO4), SCL D1 (GPIO5). Keep D3, D4 and D8 free (boot pins). ESP32: default Wire pins.
- Check the MAX30102 board: some pull SDA/SCL up to 1.8 V. Move the jumper to 3.3 V. Keep Wi-Fi on so the power bank does not switch off.
- Readings (estimates from hobby sensors): `hr` every 1 s and `spo2` every 4 s from the SparkFun library and Maxim's algorithm over a 4 s window; `skin_temp` every 2 s from the MLX90614 object temperature (non-contact, not an axillary or core temperature); `motion` every 1 s from the MPU6050.
- Flags (team values): `no_contact` for mean IR below 50,000 counts (`hr` then goes out as val 0 every 5 s) or `skin_temp` below 30 C; `settling` for the first 4 s after contact and while `skin_temp` moved more than 0.1 C in 30 s; `motion` on `hr` and `spo2` when a 1 s motion value above 0.05 g falls in the last 4 s (threshold not yet tuned on the bench).
- Single core: on the ESP8266, `HabitatNode::loop()` shares the loop with sensing, so a Wi-Fi or broker reconnect can pause it. If the pause exceeds 0.8 s the sketch prints `# fifo gap` and restarts the window instead of using a gap. On the ESP32 `HabitatNode::loop()` runs on core 0.
- With no `secrets.h` the sketch runs serial-only and prints the same contract-v1 lines (this is what the Wokwi twin runs).

### UNO+WiFi DIP switch modes (UNO+WiFi only; vendor table, unverified on this board)

A plain Arduino UNO R3 has no DIP switch: skip this section.

From the RobotDyn product page for the UNO+WiFi R3 ATmega328P+ESP8266 (robotdyn.com, listing "UNO+WiFi R3
ATmega328P+ESP8266, 32Mb flash, USB-TTL CH340G, Micro-USB"), 8-position switch, DIP 8 reserved. Re-check against
the silkscreen on the board in hand: clones differ.

| Mode | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| USB to ATmega328 (upload `exercise-uno`; also the run mode for the rig over USB) | OFF | OFF | ON | ON | OFF | OFF | OFF |
| USB to ESP8266, upload firmware | OFF | OFF | OFF | OFF | ON | ON | ON |
| USB to ESP8266, serial monitor | OFF | OFF | OFF | OFF | ON | ON | OFF |
| ATmega328 and ESP8266 linked (bridge mode) | ON | ON | OFF | OFF | OFF | OFF | OFF |
| All independent | OFF | OFF | OFF | OFF | OFF | OFF | OFF |

In linked mode the ATmega's serial pins 0/1 go to the ESP8266, so the ATmega's USB stream is not available at the
same time. For the rig the Pi needs the "USB to ATmega328" row.

## Setup (macOS or Linux, about 10 minutes plus downloads)

1. Install the CLI: `brew install arduino-cli` (macOS), or the official install script from the arduino-cli repository on the Pi. Tested with arduino-cli 1.5.1.
2. Add the board index URLs, then refresh:
   ```
   arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
   arduino-cli config add board_manager.additional_urls https://arduino.esp8266.com/stable/package_esp8266com_index.json
   arduino-cli core update-index
   ```
3. Install the pinned cores:
   ```
   arduino-cli core install esp32:esp32@3.3.12 esp8266:esp8266@3.1.2 arduino:avr@1.8.8
   ```
4. Install the pinned libraries (quote the names):
   ```
   arduino-cli lib install "ArduinoJson@7.4.3" "MQTT@2.5.3" \
     "SparkFun MAX3010x Pulse and Proximity Sensor Library@1.1.2" \
     "Adafruit BME280 Library@2.3.0" "Adafruit Unified Sensor@1.1.15" "Adafruit BusIO@1.17.4" \
     "Sensirion I2C SCD4x@1.1.0" "Sensirion Core@0.7.3" \
     "DHT sensor library@1.4.7" "HX711 Arduino Library@0.7.5" "Servo@1.3.0" \
     "BH1750@1.3.0" "MFRC522@1.4.12" "Adafruit MLX90614 Library@2.1.7"
   ```
5. For each ESP sketch, copy `secrets.example.h` to `secrets.h` and fill it in. `secrets.h` is git-ignored. Never commit it.

## Cores

| Core | Version | Licence (SPDX) | FQBN |
|---|---|---|---|
| esp32:esp32 | 3.3.12 | LGPL-2.1-or-later | `esp32:esp32:esp32` |
| esp8266:esp8266 | 3.1.2 | LGPL-2.1-or-later | `esp8266:esp8266:nodemcuv2` (`CABIN_FQBN`; use `esp8266:esp8266:d1_mini` if the board on hand is that one) |
| arduino:avr | 1.8.8 | LGPL-2.1-or-later | `arduino:avr:uno` |

The ESP cores are LGPL-2.1 but bundle Espressif's radio firmware blobs. These are public but not open source, so cite them as public.

## Libraries

| Library | Version | Licence (SPDX) | Used by |
|---|---|---|---|
| ArduinoJson | 7.4.3 | MIT | vitals, cabin |
| MQTT (256dpi, lwmqtt) | 2.5.3 | MIT | vitals, cabin |
| SparkFun MAX3010x Pulse and Proximity Sensor Library | 1.1.2 | MIT (see note) | vitals |
| Adafruit BME280 Library | 2.3.0 | BSD-3-Clause | cabin |
| Adafruit Unified Sensor | 1.1.15 | Apache-2.0 | cabin |
| Adafruit BusIO | 1.17.4 | MIT | cabin |
| Sensirion I2C SCD4x | 1.1.0 | BSD-3-Clause | cabin |
| Sensirion Core | 0.7.3 | BSD-3-Clause | cabin |
| DHT sensor library | 1.4.7 | MIT | exercise (DHT11, D40), cabin |
| HX711 Arduino Library (bogde) | 0.7.5 | MIT | exercise, only with `ENABLE_HX711=1` |
| Servo | 1.3.0 | LGPL-2.1-or-later | exercise, only with `ENABLE_SERVO=1` |
| BH1750 (optional F9) | 1.3.0 | MIT | cabin, only if built |
| MFRC522 (optional F17) | 1.4.12 | Unlicense | cabin, only if built |
| Adafruit MLX90614 Library (optional F18) | 2.1.7 | BSD-3-Clause | cabin, only if built |

Every library is OSI-approved. Optional libraries are installed but are listed in a sketch's `libraries.txt` only when that task is built. There is no MPU6050 or MLX90614 library: the vitals sketch reads their registers through `Wire` (the MLX90614 read-word with SMBus PEC is about 20 lines in the sketch). `HabitatNode` is this repository's own code (Apache-2.0) and is not listed.

Notes for the References list (S14):
- `spo2_algorithm.h` and `heartRate.h` (and their `.cpp` files) inside the SparkFun library carry Maxim Integrated notices: "Copyright (C) 2015/2016 Maxim Integrated Products, Inc., All Rights Reserved", an MIT-style permission grant, and the clause "Except as contained in this notice, the name of Maxim Integrated Products, Inc. shall not be used except as stated in the Maxim Integrated Products, Inc. Branding Policy." OSI-compatible. Credit the algorithm as "Maxim Integrated reference algorithm, via the SparkFun MAX3010x library".
- `heartRate.h` is Nathan Seidle's (SparkFun) implementation of Maxim's PBA beat detector.

## Commands

```
export CABIN_FQBN=esp8266:esp8266:nodemcuv2
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/vitals-esp32
arduino-cli compile --fqbn $CABIN_FQBN firmware/cabin-esp8266
arduino-cli compile --fqbn arduino:avr:uno firmware/exercise-uno
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266   # needs secrets.h
arduino-cli board list                                   # find $PORT
arduino-cli upload -p $PORT --fqbn <fqbn> firmware/<sketch>
arduino-cli monitor -p $PORT --config baudrate=115200
```

Host tests for the shared library (no board needed):

```
mkdir -p firmware/build
H=firmware/libraries/HabitatNode
AJ="$HOME/Documents/Arduino/libraries/ArduinoJson/src"   # ~/Arduino/libraries on the Pi
c++ -std=c++17 -Wall -Werror -I $H/src $H/test/test_ring.cpp -o firmware/build/test_ring && firmware/build/test_ring
c++ -std=c++17 -Wall -Werror -I $H/src -I "$AJ" $H/src/ReadingFormat.cpp $H/test/test_format.cpp -o firmware/build/test_format && firmware/build/test_format
c++ -std=c++17 -Wall -Werror -I $H/src $H/test/test_boot.cpp -o firmware/build/test_boot && firmware/build/test_boot
```

Each prints `ok`. `test_boot` runs the boot counter (`BootLog.h`, an append-only log in one flash sector) against a NOR
flash model with torn and refused writes; the tilt node's `run_host_tests.sh` runs it too.

UNO I/O board (`exercise-uno`) host tests, builds and the Wokwi twin:

```
firmware/exercise-uno/test/run_host_tests.sh          # pure logic: line format, commands, cal maths, NTC, pulse
arduino-cli compile --fqbn arduino:avr:uno firmware/exercise-uno   # D40 defaults: DHT11 + buzzer
arduino-cli compile --fqbn arduino:avr:uno --build-property "build.extra_flags=-DENABLE_HX711=1 -DENABLE_SERVO=1" firmware/exercise-uno
firmware/wokwi/uno-rig/check_sync.sh                  # the Wokwi copy must equal exercise-uno.ino
firmware/wokwi/uno-rig/build.sh                       # the twin build (sketch + wokwi_twin.h)
```

Every optional channel defaults to 0 except the DHT11 (D40); turn one on only when its module is wired.
`seq` is one counter shared by all channels and both nodes (`cabin-1`, `exercise-1`), so each node's `seq` has gaps.

tilt-1 node and its Wokwi twin:

```
firmware/tilt-esp8266/test/run_host_tests.sh            # pure logic: tilt debounce, heartbeat, serial line, boot log
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266
arduino-cli compile --fqbn esp32:esp32:esp32 --library firmware/libraries/HabitatNode firmware/tilt-esp8266   # the Wokwi stand-in
firmware/wokwi/tilt-esp32/check_sync.sh
```

Vitals node (archived in D40, kept as design history):

```
cp firmware/vitals-esp32/secrets.example.h firmware/vitals-esp32/secrets.h   # fill in; git-ignored
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/vitals-esp32
arduino-cli compile --fqbn esp32:esp32:esp32 --library firmware/libraries/HabitatNode firmware/vitals-esp32
firmware/vitals-esp32/test/run_host_tests.sh              # pure logic: lines, contact, MLX90614 PEC, skin flags, motion
firmware/wokwi/vitals-esp32/test/run_chip_tests.sh        # native tests of the two simulated Wokwi chips
firmware/wokwi/vitals-esp32/check_sync.sh                 # the Wokwi copy must equal vitals-esp32.ino
```
