# Firmware toolchain

Educational prototype, not a medical device. Three sketches, one shared library, exact versions below.

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
