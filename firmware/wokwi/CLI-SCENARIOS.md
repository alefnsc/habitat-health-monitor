# Wokwi CLI scenarios: not run yet

Status on 15/11: **not automated.** `wokwi-cli` is not installed on the bench laptop, there is no `WOKWI_CLI_TOKEN`,
and only `uno-rig/` has a `wokwi.toml`. CI (`.github/workflows/ci.yml`) covers the same code through host tests and
`arduino-cli` compiles, not through the simulator. This note says what a simulator run would add, so it can be set
up after the event.

## Worth automating

Only two twins would gain from a simulator test, because only they run the real sketch end to end on a simulated
board.

**`uno-rig/`** (the real `exercise-uno.ino` plus `wokwi_twin.h`, built by `./build.sh`). One scenario, at 250000 baud:
- the `# exercise-1 boot=N` banner, then `cabin-1` `cabin_temp` and `cabin_rh` lines about every 5 s, in contract v1;
- a DHT22 reading moved outside the DHT11's range gets the `out_of_range` flag. Wokwi has no DHT11, so the DHT22
  stands in; check whether the wokwi-cli scenario format can set its temperature and humidity, or else set them in
  `diagram.json`;
- `{"v":1,"cmd":"alarm","on":true}` written to serial gives `{"type":"ack","cmd":"alarm","ok":true}`, and the buzzer
  pin (D8) toggles;
- `servo`, `cal` and `tare` give `ok:false, err:"not_built"` (compiled out in D40);
- a line that is not a command gets `ok:false, err:"bad_command"`, and the board keeps running.

**`tilt-esp32/`** (the tilt sketch on an ESP32 stand-in, serial-only, with no `secrets.h`). It needs its own `wokwi.toml`
and an `esp32:esp32` build. Using the slide switch `tilt_sw`:
- one flip gives exactly one `tilt` line, about 200 ms after the flip (the debounce);
- a flip and back within about 80 ms gives no line (a bounce);
- untouched, the same value repeats every 10 s (the heartbeat).

## Not worth it here

- `full-bench/` runs only the UNO; the ESP32 and the Pi are drawings. Its custom chips (`rpi3-hub`, `nimh-pack`) would
  need wasm builds, and `test/run_chip_tests.sh` already tests the hub chip natively.
- `vitals-esp32/` is archived (D40); `test/run_chip_tests.sh` tests its two chips natively.

## To turn it on

1. Install `wokwi-cli`, and add `WOKWI_CLI_TOKEN` as a repository secret (never in a file).
2. Write the scenarios as `uno-rig/scenario.yaml` and `tilt-esp32/scenario.yaml`. Check the step names (wait for
   serial text, write to serial, set a part control, delay) against the current wokwi-cli docs.
3. Add a CI job that runs only when the secret is set: after `firmware/wokwi/uno-rig/build.sh`, run
   `wokwi-cli --timeout 20000 --scenario scenario.yaml firmware/wokwi/uno-rig`. The headless command in
   `uno-rig/README.md` already checks the first `cabin-1` line.
