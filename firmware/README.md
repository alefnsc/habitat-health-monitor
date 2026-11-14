# Firmware toolchain

Educational prototype, not a medical device. Three sketches, one shared library, exact versions below.

## Which hardware runs what (decisions D35 and D36) [confirm: hardware member to review before submission]

| Board | Runs | Link |
|---|---|---|
| Raspberry Pi 3 Model B | hub, Mosquitto, and the `cabin-1` node (`nodes/cabin_pi`, Python: BME280, SCD41, optional DHT22) | MQTT on localhost; see `docs/pi-setup.md` |
| UNO+WiFi R3, ATmega328P side | `exercise-uno`: HX711 load cell, servo, buzzer, optional NTC `skin_temp` and KY-039 `hr` (hobby estimates) | USB serial to the Pi, 250000 baud |
| UNO+WiFi R3, ESP8266 side | optional Wi-Fi bridge for the ATmega's lines; not built, may be cut | MQTT |
| Battery-powered board (ESP32 or ESP8266) | `vitals` node | Wi-Fi/MQTT |
| Wokwi | the Uno rig only (`firmware/wokwi/uno-rig/`); Wokwi has no ESP8266 | n/a |

`firmware/cabin-esp8266` is still the empty skeleton. The Pi node replaces it, and it stays only as a fallback.

### UNO+WiFi DIP switch modes (vendor table, unverified on this board)

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
     "OneWire@2.3.8" "DallasTemperature@4.0.6" \
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
| OneWire | 2.3.8 | MIT (permissive notice in source) | vitals |
| DallasTemperature | 4.0.6 | MIT | vitals |
| Adafruit BME280 Library | 2.3.0 | BSD-3-Clause | cabin |
| Adafruit Unified Sensor | 1.1.15 | Apache-2.0 | cabin |
| Adafruit BusIO | 1.17.4 | MIT | cabin |
| Sensirion I2C SCD4x | 1.1.0 | BSD-3-Clause | cabin |
| Sensirion Core | 0.7.3 | BSD-3-Clause | cabin |
| DHT sensor library | 1.4.7 | MIT | cabin |
| HX711 Arduino Library (bogde) | 0.7.5 | MIT | exercise |
| Servo | 1.3.0 | LGPL-2.1-or-later | exercise |
| BH1750 (optional F9) | 1.3.0 | MIT | cabin, only if built |
| MFRC522 (optional F17) | 1.4.12 | Unlicense | cabin, only if built |
| Adafruit MLX90614 Library (optional F18) | 2.1.7 | BSD-3-Clause | cabin, only if built |

Every library is OSI-approved. Optional libraries are installed but are listed in a sketch's `libraries.txt` only when that task is built. There is no MPU6050 library: the vitals sketch reads its registers through `Wire`. `HabitatNode` is this repository's own code (Apache-2.0) and is not listed.

Notes for the References list (S14):
- `spo2_algorithm.h` and `heartRate.h` (and their `.cpp` files) inside the SparkFun library carry Maxim Integrated notices: "Copyright (C) 2015/2016 Maxim Integrated Products, Inc., All Rights Reserved", an MIT-style permission grant, and the clause "Except as contained in this notice, the name of Maxim Integrated Products, Inc. shall not be used except as stated in the Maxim Integrated Products, Inc. Branding Policy." OSI-compatible. Credit the algorithm as "Maxim Integrated reference algorithm, via the SparkFun MAX3010x library".
- `heartRate.h` is Nathan Seidle's (SparkFun) implementation of Maxim's PBA beat detector.
- The OneWire notice is the MIT text, with Dallas Semiconductor copyright lines in places.

## Commands

```
export CABIN_FQBN=esp8266:esp8266:nodemcuv2
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/vitals-esp32
arduino-cli compile --fqbn $CABIN_FQBN firmware/cabin-esp8266
arduino-cli compile --fqbn arduino:avr:uno firmware/exercise-uno
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
```

Each prints `ok`.

Exercise rig (Uno) host tests and the optional analog channels:

```
firmware/exercise-uno/test/run_host_tests.sh          # pure logic: line format, commands, cal maths, NTC, pulse
arduino-cli compile --fqbn arduino:avr:uno --build-property "build.extra_flags=-DENABLE_NTC=0 -DENABLE_KY039=0" firmware/exercise-uno
firmware/wokwi/uno-rig/check_sync.sh                  # the Wokwi copy must equal exercise-uno.ino
```

`ENABLE_NTC` and `ENABLE_KY039` default to 1; turn a channel off when its module is not wired, so a floating analog pin never publishes numbers.
`seq` is one counter shared by all channels, so `load_raw` has gaps when NTC or KY-039 lines are interleaved.
