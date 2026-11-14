# Wokwi twin of the exercise rig (Arduino Uno)

Educational prototype, not a medical device. This is a simulation: every part below is simulated
and labelled so in the diagram. Wokwi has no ESP8266, so the twin is one Uno running the real
`firmware/exercise-uno` sketch. The UNO+WiFi board's ESP8266 side is not simulated.

| Simulated part | Stands in for | Sketch pin |
|---|---|---|
| `wokwi-hx711` (type 50kg) | HX711 and load cell | DT D3, SCK D4 |
| `wokwi-servo` | dial servo | PWM D6 |
| `wokwi-buzzer` | alarm buzzer | pin 2 to D8 |
| `wokwi-ntc-temperature-sensor` | NTC skin probe (`skin_temp`, `dev` NTC, hobby estimate) | OUT to A0 |
| `wokwi-potentiometer`, labelled "pulse stand-in (simulated)" | KY-039 pulse module (`hr`, `dev` KY039) | SIG to A1 |

Part and pin names follow docs.wokwi.com/parts/. They were checked against the docs pages, not by
a headless run (see "Headless run").

**Saved project (share link):** https://wokwi.com/projects/480675272836723713. It matches commit c0d2b38 file for file.

## Open it on wokwi.com

1. Start a new **Arduino Uno** project.
2. Paste these three files over the project's files:
   - `firmware/wokwi/uno-rig/sketch.ino` into `sketch.ino`
   - `firmware/wokwi/uno-rig/diagram.json` into `diagram.json`
   - `firmware/wokwi/uno-rig/libraries.txt` into `libraries.txt`
3. Press Start. The serial monitor shows `# exercise-1 boot=1`, `# cal missing`, then about one
   contract-v1 line per HX711 sample. Type commands into the monitor, one JSON line each, for example
   `{"v":1,"cmd":"servo","angle_deg":90}`, `{"v":1,"cmd":"alarm","on":true}`,
   `{"v":1,"cmd":"cal","mass_kg":2.0}`.

What differs from the bench:
- The simulated HX711 has its own raw range and timing, so the `# rate_sps` line will not read 80
  and the calibration numbers mean nothing for the real cell. Use it to check the protocol only.
- The potentiometer is not a pulse. Turn it back and forth about once a second to make "beats";
  otherwise `hr` reports `no_contact` or `settling`. The value is a simulation artefact, not a heart rate.
- The NTC part is set to 34 C. It reports `settling` for its first 30 s.

## Keep the copy in sync

`sketch.ino` must be byte-for-byte `firmware/exercise-uno/exercise-uno.ino`.
- `./sync.sh` refreshes the copy; `./check_sync.sh` fails when they differ.
- `pytest hub/tests/test_firmware_exercise.py` fails when they differ.

## Headless run (wokwi-cli)

```
./build.sh                                   # arduino-cli compile into ./build (git-ignored)
export WOKWI_CLI_TOKEN=...                   # from the Wokwi CI dashboard, never committed
wokwi-cli --timeout 8000 --expect-text '# exercise-1 boot=' --serial-log-file /tmp/uno-rig.log .
```

`wokwi.toml` points at `build/exercise-uno.ino.hex` and `.elf`. Status: the sketch compiles for
`arduino:avr:uno`; the headless run is pending (no token or `wokwi-cli` in the build environment).
