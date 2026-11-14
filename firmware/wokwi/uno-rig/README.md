# Wokwi twin of the UNO I/O board (Arduino Uno, decision D40)

Educational prototype, not a medical device. This is a simulation, and every part below is simulated and labelled so in
the diagram. Wokwi has no ESP8266, so the twin is one Uno running the real `firmware/exercise-uno` sketch. The UNO+WiFi
board's ESP8266 side is unused in D40.

| Simulated part | Stands in for | Sketch pin |
|---|---|---|
| `wokwi-dht22`, labelled "DHT11 stand-in (simulated)" | DHT11 (`cabin_temp`, `cabin_rh`, node `cabin-1`, dev `DHT11`, hobby estimate) | data (SDA) to D2 |
| `wokwi-buzzer` | alarm buzzer | pin 2 to D8 |

Part and pin names follow docs.wokwi.com/parts/ (read 2026-11-14).

**Saved project (share link, unchanged since D35):** https://wokwi.com/projects/480675272836723713. The D40 contents
replace the old exercise rig (HX711, servo, NTC, pulse potentiometer) in place. Saved 2026-11-14 14:30 (UTC−03:00), and
renamed "UNO I/O board twin". The four files match commit 8a38e07 byte for byte (SHA-256 checked after a reload).
A run showed `cabin-1` lines every 5 s, `alarm` acked `ok:true`, and `servo` answered `not_built`.

## Real bench wiring (also written on the Wokwi canvas)

The canvas is the wiring map for the real board, an Arduino UNO R3 or the UNO+WiFi's ATmega side. Both run the same
`arduino:avr:uno` firmware. Wire colours on the canvas: red 5V, black GND, green D2, purple D8.

| Module | Module pin | Board pin |
|---|---|---|
| DHT11 module | S (data) | D2 |
| DHT11 module | + | 5V |
| DHT11 module | − | GND |
| Buzzer module | S | D8 |
| Buzzer module | − | GND |
| Buzzer module | middle pin | 5V, **only if it is printed + or VCC** |

Match each pin by its printed letter, not by its position: module batches order their pins differently.

## What runs where (also written on the Wokwi canvas)

- **Code:** the same sketch as the real board, `firmware/exercise-uno/exercise-uno.ino`. `hub/tests/test_firmware_exercise.py`
  checks it byte for byte.
- **Twin settings:** `wokwi_twin.h` is the one extra file. The sketch includes it only when it exists, and the real sketch
  folder has none. It sets `DHT_TYPE DHT22`, because Wokwi has no DHT11, and `BUZZER_PASSIVE 1`, because the Wokwi
  buzzer is a piezo played with `tone()`.
- **Role:** reads the cabin temperature and humidity, and sounds the habitat alarm when the hub sends a command.
- **Link:** USB serial at 250000 baud, one contract-v1 JSON reading per line. Commands come in on the same port, and each
  gets one ack line.
- **Config (D40 defaults):** `ENABLE_DHT=1`; `ENABLE_HX711`, `ENABLE_SERVO`, `ENABLE_NTC` and `ENABLE_KY039` are 0.

| Part | Pin | Produces / does | On the bench |
|---|---|---|---|
| DHT11 stand-in (simulated DHT22) | D2 | `cabin_temp` (C) and `cabin_rh` (%) every 5 s, node `cabin-1` | DHT11 module |
| Alarm buzzer | D8 | 500 ms on, 500 ms off while the alarm is on | active or passive buzzer module |

## Open it on wokwi.com

1. Open the saved project, or start a new **Arduino Uno** project.
2. Paste these four files over the project's files:
   - `firmware/wokwi/uno-rig/sketch.ino` into `sketch.ino`;
   - `firmware/wokwi/uno-rig/wokwi_twin.h` into a new tab `wokwi_twin.h`;
   - `firmware/wokwi/uno-rig/diagram.json` into `diagram.json`;
   - `firmware/wokwi/uno-rig/libraries.txt` into `libraries.txt`.
3. Press Start. The serial monitor shows:
   - `# exercise-1 boot=1`;
   - `# channels dht=on hx711=off servo=off ntc=off ky039=off buzzer=passive`;
   - from about 2 s, two `cabin-1` lines every 5 s.
4. Click the DHT22 and move its sliders: the next lines follow.
5. Type commands into the monitor, one JSON line each:
   - `{"v":1,"cmd":"alarm","on":true}` sounds the buzzer (ack `ok:true`);
   - `{"v":1,"cmd":"alarm","on":false}` stops it;
   - `{"v":1,"cmd":"servo","angle_deg":90}` answers `ok:false` with `err` `not_built`, because there is no servo on this
     board.

**What differs from the bench:**
- The DHT22 reports tenths of a degree and of a percent. The real DHT11 reports whole degrees, about ±2 °C and ±5 %RH.
- The readings still say `dev` `DHT11`, because the sketch is the bench sketch.
- Temperatures above 50 °C or humidity outside 20–90 % carry `out_of_range`, which are the DHT11's limits.

## Keep the copy in sync

`sketch.ino` must be byte-for-byte `firmware/exercise-uno/exercise-uno.ino`.
- `./sync.sh` refreshes the copy, and `./check_sync.sh` fails when they differ.
- `pytest hub/tests/test_firmware_exercise.py` also fails when they differ.

## Headless run (wokwi-cli)

```
./build.sh                                   # compiles sketch.ino + wokwi_twin.h into ./build (git-ignored)
export WOKWI_CLI_TOKEN=...                   # from the Wokwi CI dashboard, never committed
wokwi-cli --timeout 8000 --expect-text '"node":"cabin-1"' --serial-log-file /tmp/uno-rig.log .
```

`wokwi.toml` points at `build/exercise-uno.ino.hex` and `.elf`.
