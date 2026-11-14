# Wokwi twin of the vitals node (ESP32 stands in for the NodeMCU Amica)

Educational prototype, not a medical device. Everything in this simulation is simulated and labelled so
in the diagram. Wokwi has no ESP8266, so an ESP32 DevKit runs the real `firmware/vitals-esp32` sketch.
The sketch is the same file; only the board and the sensors differ.

| Part in the diagram | What it is | I2C address |
|---|---|---|
| `wokwi-esp32-devkit-v1` | stands in for the NodeMCU Amica (SDA GPIO21, SCL GPIO22 here; D2/D1 on the real board) | |
| `chip-max30102` ("MAX30102 pulse sensor (simulated)") | custom chip: synthetic PPG, PART_ID 0xFF = 0x15, FIFO | 0x57 |
| `chip-mlx90614` ("MLX90614 GY-906 (simulated)") | custom chip: SMBus RAM 0x07 object temperature, with PEC | 0x5A |
| `wokwi-mpu6050` ("MPU6050 (simulated)") | Wokwi's native part | 0x68 |

The synthetic PPG is a smooth beat train with a pulse rate, SpO2 ratio and finger state set by controls. It
exercises the firmware path (FIFO, 4 s window, flags, publishing). It is not a model of a finger, of the real
chip's front end, or of any person: any heart rate or SpO2 shown here is a simulation artefact.

## Open it on wokwi.com

Saved project (same seven files as this folder at commit 8863ad6): https://wokwi.com/projects/480680478751478785

To rebuild it from scratch:

1. Start a new **ESP32** project (Arduino).
2. Make these seven files in the project and paste the contents from this folder
   (`firmware/wokwi/vitals-esp32/`):

   | Paste into | Source file here |
   |---|---|
   | `sketch.ino` | `sketch.ino` |
   | `diagram.json` | `diagram.json` |
   | `libraries.txt` | `libraries.txt` |
   | `max30102.chip.json` | `max30102.chip.json` |
   | `max30102.chip.c` | `max30102.chip.c` |
   | `mlx90614.chip.json` | `mlx90614.chip.json` |
   | `mlx90614.chip.c` | `mlx90614.chip.c` |

   Add each chip with the blue "+" button, then "Custom Chip", or create the files directly. Wokwi builds the
   chip C files to WebAssembly itself.
3. Press Start. With no `secrets.h` the sketch runs in serial-only mode and prints one contract-v1 line per
   reading; the banner says `# vitals-1 serial-only mode (no secrets.h)`. Expect `# max3010x found addr=0x57`,
   `# mpu6050 addr=0x68 who_am_i=...`, `# mlx90614 found addr=0x5A`, then:
   - `motion` every 1 s (MPU6050 at rest, near 0 g),
   - `skin_temp` every 2 s (MLX90614, 34.5 C by default; `no_contact` below 30 C, `settling` for the first 30 s),
   - `hr` every 1 s and `spo2` every 4 s once a 4 s window has filled, `settling` for the first 4 s.
4. During the run, click the MAX30102 chip to move the sliders: finger on or off (off gives `no_contact` and
   `hr` with val 0 every 5 s), pulse rate, SpO2. Click the MLX90614 chip for the object temperature. Click
   the MPU6050 and change its acceleration to see `motion` and the `motion` flag on `hr` and `spo2`.

## Keep the copy in sync

`sketch.ino` must be byte-for-byte `firmware/vitals-esp32/vitals-esp32.ino`. `./sync.sh` refreshes the copy,
`./check_sync.sh` fails when they differ, and `pytest hub/tests/test_firmware_vitals.py` fails too.

## What was and was not verified

- Verified here: the sketch compiles for `esp8266:esp8266:nodemcuv2` and `esp32:esp32:esp32`, in both modes; the
  pure logic has host tests (`firmware/vitals-esp32/test/run_host_tests.sh`); and `test/run_chip_tests.sh`
  compiles both chip C files natively against a host stand-in for `wokwi-api.h` (written from the Wokwi chips
  API docs, not the real header), plays the SparkFun library's bus traffic into the MAX30102 chip, and runs
  Maxim's reference algorithm on its output (72 bpm and 97 % come back as about 75 and 97; 120 bpm and 92 % as
  about 125 and 92). The MLX90614 chip's output is decoded by the firmware's own decoder, PEC included.
- Not verified: the chips have not been built with the Wokwi chip toolchain (not available locally), and the
  diagram has not been opened in Wokwi. Part type names and pin names (`esp:D21`, `esp:D22`, `esp:3V3`,
  `esp:GND.1`, the chip pins) follow the Wokwi docs and diagram conventions as recalled; the ESP32 DevKit pin
  names in particular were not on a docs page. If Wokwi marks a connection red, fix the pin name in
  `diagram.json` and note it here.
- Not simulated: Wi-Fi/MQTT (no broker), the 1.8 V pull-up trap on some MAX30102 boards, the single-core
  `fifo gap` behaviour of the ESP8266, and real I2C timing at 100 kHz.
