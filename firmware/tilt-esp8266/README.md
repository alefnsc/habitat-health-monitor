# tilt-1: sealed tilt switch node (D39)

An independent witness of when each exercise rep turns around. The switch trips when the weight
tilts past its trip angle (roughly 45°, unspecified by the module) and releases when it comes back,
so in a rep it rises during the lift and falls during the lowering. The hub compares that interval
with the camera's turnaround (`GET /api/reps`, field `tilt`). It measures no angle and no gravity.

## Wiring (NodeMCU Amica)

| KY-017 pin | NodeMCU |
|---|---|
| signal | D5 (GPIO14) |
| VCC | 3V3 |
| GND | GND |

- Module batches differ in pin order: read the silkscreen and confirm the switch with a meter before power.
- Keep D1/D2 free (I2C for a later MPU6050) and D3, D4, D8 free (boot pins).
- This node is never worn on the body.

## Power (D40): a cell pack, no cable

The pod rides on the weight, so the node runs on its own cells and nothing on the held weight is cabled to the hub.

- **Chosen pack: 4 × Ni-MH AA in series** (about 4.8 V nominal, 5.6 V fresh), wired to the NodeMCU's **VIN** and **GND**
  pins. The board's regulator makes 3.3 V. Solder the leads, or use a 4-cell holder. With 2,450 mAh cells and Wi-Fi on
  (about 80 mA), the pack lasts roughly a day.
- **Other pack: 2 × alkaline AA or AAA in series** (3.0 to 3.2 V fresh), wired to **3V3** and **GND**. This bypasses the
  regulator and lasts about 15 hours.
- **Never 2 cells on VIN.** The regulator needs more than about 4.5 V. Two Ni-MH on 3V3 are too low as well (2.4 to 2.8 V).
- **Never 3 or more cells on 3V3.** More than 3.6 V on 3V3 destroys the board.
- **One kind of cell per pack.** Never mix types, brands or charge levels: charge Ni-MH cells together.
- **The KY-017 stays on 3V3 and GND**, never on VIN, so the D5 input never sees more than 3.3 V.
- **No CR2032.** A coin cell cannot supply the Wi-Fi bursts (170 to 300 mA): the voltage collapses and the board resets.
- **Flashing.** Unplug the pack before you plug USB in to flash, and plug it back after.
- **Twin.** The Wokwi twin of this node is in `firmware/wokwi/tilt-esp32`.

## Safety: the capsule holds mercury

- The pod is **sealed**: heat-shrink over the capsule, the module inside a small closed box. It is never opened.
- Only **adult** team members handle it. If the glass breaks, follow `docs/safety-checklist.md`.
- The neodymium magnet is glued to the outside of the box and sticks the pod to the steel weight. It can pinch fingers.

## Boot number

Every reading carries the node's boot number; the hub keys readings on `(node, boot, seq)`. On the bench
(2026-11-15) the number went 4, 7, 9, 8, 10, 11, 1, 2 within an hour, because the EEPROM emulation erases its sector
and writes it back on every boot and that write failed or was cut on the pack. The library now keeps the number as an
append-only log in that sector (`firmware/libraries/HabitatNode/src/BootLog.h`, decision D42): one 8-byte write per
boot, no erase until 512 boots have passed, and a torn write still yields a higher number next time. The first boot
after flashing this version is 2. The hub stores a repeated number that carries a different sample under a `clash`
number instead of dropping it. In serial-only mode (no `secrets.h`, the Wokwi twin) `boot` stays the constant 1.

## Set-up check

1. Mount the pod so the switch **reads 0** with the weight at rest. Check the live `tilt` value with `curl -s 'http://<hub>:8000/api/readings?ind=tilt&limit=5'` (newest 5 rows, oldest first; `val` is the state), or read the node's serial monitor, which prints a `# pub tilt <val> ...` line for each reading it publishes.
2. If it reads 1 at rest, turn the pod around on the weight (or rebuild with `-DTILT_ACTIVE_LOW=0`).
3. Tilt the weight slowly past the trip angle: the value must go to 1, and back to 0 when it returns.

## What the offset includes

The `offset_ms` that `GET /api/reps` reports (midpoint of the switch interval minus the camera turnaround) carries some known biases:

- The debounce is 200 ms: the mercury bounces for up to about 150 ms at each edge (bench check 14/11). It stamps the accept time, so both edges read about +200 ms late, inside the hub's ±500 ms witness window.
- The camera turnaround is the first sample at the top level, so the offset leans positive.
- A pause at the top shifts the switch midpoint by about half the pause.
- A rise then fall shorter than a Wi-Fi or broker reconnect stall can be missed entirely. That reads as `seen: false`, which is honest, not an error.

## Build

    cp secrets.example.h secrets.h   # then fill in Wi-Fi and broker values
    arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266

Host tests (no board): `firmware/tilt-esp8266/test/run_host_tests.sh` prints `ok`.
