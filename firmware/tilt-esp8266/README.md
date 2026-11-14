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
- Power over USB from the hub. This node is never worn on the body.

## Safety: the capsule holds mercury

- The pod is **sealed**: heat-shrink over the capsule, the module inside a small closed box. It is never opened.
- Only **adult** team members handle it. If the glass breaks, follow `docs/safety-checklist.md`.
- The neodymium magnet is glued to the outside of the box and sticks the pod to the steel weight. It can pinch fingers.

## Set-up check

1. Mount the pod so the switch **reads 0** with the weight at rest. Check the live `tilt` value with `curl -s 'http://<hub>:8000/api/readings?ind=tilt&limit=5'` (newest 5 rows, oldest first; `val` is the state), or read the node's serial monitor, which prints a `# pub tilt <val> ...` line for each reading it publishes.
2. If it reads 1 at rest, turn the pod around on the weight (or rebuild with `-DTILT_ACTIVE_LOW=0`).
3. Tilt the weight slowly past the trip angle: the value must go to 1, and back to 0 when it returns.

## What the offset includes

The `offset_ms` that `GET /api/reps` reports (midpoint of the switch interval minus the camera turnaround) carries some known biases:

- The debounce stamps the accept time, so both edges read about +30 ms late.
- The camera turnaround is the first sample at the top level, so the offset leans positive.
- A pause at the top shifts the switch midpoint by about half the pause.
- A rise then fall shorter than a Wi-Fi or broker reconnect stall can be missed entirely. That reads as `seen: false`, which is honest, not an error.

## Build

    cp secrets.example.h secrets.h   # then fill in Wi-Fi and broker values
    arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266

Host tests (no board): `firmware/tilt-esp8266/test/run_host_tests.sh` prints `ok`.
