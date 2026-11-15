# Pluggable sensor modules and board configuration — design (D46)

Status: design sections approved one by one by the team owner, 2026-11-15 (UTC−03:00), and the written spec,
including the additions listed in §2, approved by the owner the same day. This is **post-event** work. It does not change the build submitted to NASA Space Apps on
2026-11-15, and nothing here is implemented yet.

The team owner's request: "acoplability of new modules sensors + config board output number etc."

## 1. Goal

Adding a sensor to the habitat, moving it to another pin, or adding a second board of a kind should mean editing
one or two data files, not about fifteen files in four languages. The hub, the console, the Wokwi twins and the
tests follow from those files, and CI fails when any copy falls behind them.

Two things do not change: the contract-v1 wire format (the same JSON line, field for field), and where health
limits come from (`data/thresholds.json`, with its NASA and clinical sources).

## 2. Decisions taken in the brainstorm

| # | Question | Decision |
|---|---|---|
| Q1 | What "board output config" covers | All four: pin assignment; which channels a board publishes and how often; actuator outputs (buzzer, servo) and their commands; how many boards and nodes the habitat runs. |
| Q2 | How the hub learns about a module | A descriptor file in the repository, checked by CI. The hub loads all descriptors at start (a restart, no hub code). Nodes do not announce themselves. |
| Q3 | How firmware gets pins, channels and rates | A header generated at build time from the descriptors. A change means a reflash. No run-time configuration. |
| Q4 | Console | Generic lanes drawn from the descriptors; bands still from `data/thresholds.json`; panel cards and special views stay hand-built. |
| Q5 | Wokwi twins | Check, do not generate, `diagram.json`. Generate `wokwi_twin.h`. |
| Q6 | Worked example | CO2 on the UNO in full, then the archived vitals node in short. Section 7 review: the CO2 example adds a BME280 (see §11.1). |
| Q7 | Descriptors and `hub/contract.py` | The descriptors become the single source; `contract.py` builds its tables from them. |
| — | Approach | A: registry JSON plus one generator; generated files are committed and CI fails on any difference. Rejected: B, a run-time registry with hand-written firmware and C-parsing parity tests; C, generation at build time with nothing committed, which every `arduino-cli` build, IDE build and Wokwi paste would then depend on. |

Added while writing, after the sections were approved, and approved with the written spec: safety rule S6
(logic level, §5.4), the `default` board field (§4.4), commands routed through disabled placements (§6.4), and a
looser RAM gate for "every placement enabled" builds (§10).

## 3. What adding a sensor touches today

Read from `main` at `239924d`:

| Layer | Files |
|---|---|
| Firmware | the sketch's pin constants and `ENABLE_*` flags (`firmware/exercise-uno/exercise-uno.ino`, `firmware/tilt-esp8266/tilt-esp8266.ino`); the `Ind`/`Dev` enums and the name, unit and decimals tables in `firmware/libraries/HabitatNode/src/ReadingFormat.h` and `.cpp` |
| Hub | `INDICATORS`, `DEVICES`, `NODES`, `CABIN_INDS`, `BODY_INDS`, `INTAKE_CEILINGS`, `BODY_MASS_RANGE` in `hub/contract.py`; `SERIAL_NODES` and `command_topic()` in `hub/commands.py`; `QUIET_INDS` and the `cabin_co2` special case in `hub/ingest.py`; `UNGATED_INDS` in `hub/assess.py` |
| Data | `data/thresholds.json` |
| Console | the `Ind` union in `console/src/contract.ts`; `LANES` in `console/src/model/lanes.ts`; `copy.ts`, `format.ts`, the panel bands and "missing" models |
| Wokwi | each twin's `diagram.json`; `sync.sh` and `check_sync.sh`; the cabin bands copied into `firmware/wokwi/full-bench/rpi3-hub.chip.c` |
| Tests | substring checks on `ReadingFormat.*` in `hub/tests/test_contract.py` and `hub/tests/test_firmware_tilt.py`, which break on every new enum |

The copies are checked against each other only loosely, and a new part has to be added by hand in every row.

## 4. The registry

### 4.1 Files

A new top-level folder, `registry/`, is the one source of truth.

| File | One per | Says |
|---|---|---|
| `registry/indicators.json` | contract | every indicator: id, unit, decimals, scope, label, the hub rules that are fields today (§4.2), lane hint |
| `registry/core.json` | contract | sources, flags, crews, rep sources, exercises, and the producers that are not boards (`manual`, `camera`, `nasa`, `food`, `ring-1`, `sim-1`, `strap-1`) with their devices (`manual`, `camera`, `DONKI`, `OSDR`, `catalog`, `RING`, `H10`) |
| `registry/parts/<id>.json` | part type (`DHT11`, `SCD41`, `KY017`, `buzzer-passive`, …) | what the part measures or drives and how; no pins chosen |
| `registry/boards/<board>.json` | physical board (`uno-1`, `tilt-1`, `hub`, `vitals-1`) | MCU, link, power, node ids, and each part's placement: pins, rate, node |

All files are JSON (the repository's data format; Python reads it with the standard library) and carry
`"schema": 1`. A `note` string is allowed anywhere for comments, as in `data/thresholds.json`.

How much work each kind of change needs:

| Change | Work |
|---|---|
| A known part on another pin, or on a new board (a second DHT11 as `cabin-2` on a NodeMCU) | edit or add a board file, run `gen`, reflash |
| A new part type (the SCD41) | one part file, plus one driver written once in `firmware/libraries/HabitatParts/` with a host test of its pure block; the hub, the console and the Wokwi check need nothing beyond the files |
| A new indicator (say `cabin_voc`) | one entry in `indicators.json`, plus rules in `data/thresholds.json` with their sources if it is to be judged; its console lane follows from the lane hint |
| A new kind of command | still code in `hub/commands.py` (argument rules) and in the sketch |

A part's sensor range only decides `out_of_range`. It never makes a value healthy or unhealthy; that stays with
`data/thresholds.json`.

### 4.2 `indicators.json`

One object per indicator, in a list whose order is the display order of the generated enums.

| Field | Meaning | Replaces |
|---|---|---|
| `id`, `unit`, `decimals` | as in the contract; decimals feed `ReadingFormat` | `INDICATORS`, `kIndUnits`, `kDecimals` |
| `scope` | `cabin`, `body`, `intake`, `exercise`, `environment` or `other` | `CABIN_INDS`, `BODY_INDS`, `INTAKE_INDS`, and `CREW_SCOPED` (= `body` and `intake`) |
| `label` | human label, English | lane labels in `lanes.ts` |
| `reject_outside` | `[lo, hi]`: the hub rejects values outside with `bad_value:val` | `INTAKE_CEILINGS`, `BODY_MASS_RANGE`; present on those 11 indicators only, so behaviour is unchanged |
| `quiet` | stored, never assessed, outboxed or pushed one by one | `QUIET_INDS` (`load_raw`) |
| `assess` | `false`: never judged against a rule | `UNGATED_INDS` (`motion`, `load_raw`, `tilt`) |
| `derived` | `{ "from": "cabin_co2", "fn": "ppco2" }`: computed by the hub, refused from producers | `DERIVED`, and `if stored.ind == "cabin_co2"` in `ingest.py`; the maths stays in `hub/derive.py`, looked up by `fn` |
| `lane` | `{ "label", "window", "order", "optional" }`: the console draws a lane | the seven reading lanes in `LANES` |
| `codes` | allowed `code` values | `SYMPTOM_CODES` (on `symptom`) |

### 4.3 Part files

```json
{ "schema": 1, "id": "DHT11", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "DHT",
  "pins": [{ "role": "data", "kind": "digital" }],
  "supply_v": [3.3, 5.5], "rails": ["5V", "3V3"], "io_v": [3.3, 5.5],
  "contact": "none", "hazards": [],
  "outputs": [
    { "ind": "cabin_temp", "range": [0, 50],  "flags": ["out_of_range", "no_contact"] },
    { "ind": "cabin_rh",   "range": [20, 90], "flags": ["out_of_range", "no_contact"] }],
  "period_ms": { "min": 1000, "default": 5000 },
  "params": { "fails_for_no_contact": { "min": 1, "max": 10, "default": 3 } },
  "wokwi": { "part": "wokwi-dht22", "label": "DHT11 stand-in (simulated)", "pins": { "data": "SDA" },
             "twin_defines": { "DHT_TYPE": "DHT22" } } }
```

| Field | Meaning |
|---|---|
| `id` | for a sensor, the contract's `dev`; for an actuator, a part name (`buzzer-passive`, `servo`) |
| `kind` | `sensor` or `actuator` |
| `driver` | `inline` (code lives in the sketch, as every part on the bench today) or the name of a `HabitatParts` header (`SCD41`) |
| `macro` | prefix of the generated macros (`DHT` → `ENABLE_DHT`, `PIN_DHT`) |
| `pins` | roles with a kind: `digital`, `analog`, `pwm`, `i2c-sda`, `i2c-scl` |
| `i2c` | for I2C parts: `{ "addr": "0x62", "max_hz": 400000 }` |
| `supply_v`, `rails`, `io_v` | supply range, rails it may be powered from, and the logic levels its pins accept |
| `contact` | `none` or `body` (worn or touching a person) |
| `hazards`, `handling` | e.g. `["mercury"]` with `"handling": "adults_only"` |
| `outputs` | per indicator: sensor `range`, the `flags` it can raise, and `needs` for a flag that depends on another indicator (`{ "motion": "motion" }`, §12) |
| `commands` | for actuators: the commands they serve (`["alarm"]`) |
| `period_ms` | allowed sample period and default |
| `params` | part-specific settings with limits and default (`debounce_ms`, `heartbeat_ms`, `active_low`) |
| `wiring_notes` | sentences copied into the generated checklist (§5.5) |
| `wokwi` | `part` (a Wokwi part) or `chip` (a custom chip in `firmware/wokwi/parts/`), canvas `label` (must say "simulated"), role → part pin map, `twin_defines` |

A part file with no placement is valid. The devices in today's `DEVICES` that no board uses (`DS18B20`, `BH1750`,
`MH-Z19`, …) keep a part file each, so `DEVICES` stays the same set.

### 4.4 Board files

```json
{ "schema": 1, "board": "uno-1", "status": "active", "mcu": "atmega328p", "fqbn": "arduino:avr:uno",
  "sketch": "firmware/exercise-uno", "twins": ["firmware/wokwi/uno-rig", "firmware/wokwi/full-bench"],
  "link": { "transport": "serial", "baud": 250000 }, "power": { "source": "usb-host" },
  "nodes": ["exercise-1", "cabin-1"], "ack_node": "exercise-1",
  "placements": [
    { "part": "DHT11", "node": "cabin-1", "pins": { "data": "D2" }, "period_ms": 5000, "supply": "5V" },
    { "part": "buzzer-passive", "node": "exercise-1", "pins": { "signal": "D8" } },
    { "part": "HX711", "node": "exercise-1", "pins": { "dout": "D3", "sck": "D4" }, "enabled": false },
    { "part": "servo", "node": "exercise-1", "pins": { "signal": "D6" }, "enabled": false },
    { "part": "NTC", "node": "exercise-1", "pins": { "out": "A0" }, "enabled": false },
    { "part": "KY039", "node": "exercise-1", "pins": { "out": "A1" }, "enabled": false } ] }
```

```json
{ "schema": 1, "board": "tilt-1", "status": "active", "mcu": "esp8266", "fqbn": "esp8266:esp8266:nodemcuv2",
  "sketch": "firmware/tilt-esp8266", "twins": ["firmware/wokwi/tilt-esp32"],
  "link": { "transport": "mqtt" },
  "power": { "source": "pack", "pack": { "cells": 4, "chemistry": "nimh", "size": "AA", "pin": "VIN" } },
  "nodes": ["tilt-1"],
  "placements": [
    { "part": "KY017", "node": "tilt-1", "pins": { "signal": "D5" }, "supply": "3V3", "enclosure": "sealed",
      "params": { "debounce_ms": 200, "heartbeat_ms": 10000, "active_low": 1 } } ] }
```

| Field | Meaning |
|---|---|
| `status` | `active` (on the bench) or `archived` (validated and compiled in CI, not on the bench; `vitals-1`) |
| `default` | `true` on the board a sketch builds for when no `-DBOARD_<ID>` flag is given; required, on exactly one board, when more than one board runs the same sketch |
| `mcu` | `atmega328p`, `esp8266`, `esp32` or `host` (the hub computer) |
| `fqbn`, `sketch`, `twins` | how CI builds it and which Wokwi folders mirror it |
| `link` | `{ "transport": "serial", "baud": … }` or `{ "transport": "mqtt" }`; `null` for `host` |
| `power.source` | exactly one of `usb-host` (a computer: laptop or Pi), `usb-bank` (a protected power bank), `pack` (cells, with `pack`), `mains` (a wall supply) |
| `nodes`, `ack_node` | the node ids this board speaks for; the node that carries acks |
| `placements[]` | `part`, `node`, `pins` (role → board pin label), `period_ms`, `params`, `supply` (rail; required when the part lists `rails`), `outputs` (a subset of the part's outputs; default all), `enabled` (default `true`), `enclosure`, `level_shifted`, `as` (a macro prefix when one part type is placed twice on a board) |

`registry/boards/hub.json` is `{ "board": "hub", "mcu": "host", "link": null, "power": { "source": "mains" },
"nodes": [], "placements": [] }`.

### 4.5 MCU tables

The tool keeps one table per MCU kind, written once from the board documentation already in the repository
(`firmware/README.md`, the sketches' headers, D40):

| MCU | Pin labels → GPIO | Reserved | I2C | Logic level | Rails | Power windows |
|---|---|---|---|---|---|---|
| `atmega328p` (UNO) | `D2` → 2, `A0` → A0, … | `D0`, `D1` (USB serial) | `A4` SDA, `A5` SCL | 5 V | `5V`, `3V3` | no pack window: USB power only, as on the bench |
| `esp8266` (NodeMCU) | `D5` → 14, `D1` → 5, `D2` → 4, … | `D3`, `D4`, `D8` (boot pins) | `D2` SDA, `D1` SCL | 3.3 V | `3V3`; `VIN` for power in | VIN (4.5, 6.0] V (6.0 is a team limit); 3V3 [2.7, 3.6] V |
| `esp32` (DevKit: the Wokwi stand-in) | GPIO numbers | GPIO 0, 2, 5, 12, 15 (strapping) and 6–11 (flash) | GPIO 21 SDA, 22 SCL | 3.3 V | `3V3`; `VIN` | as for the ESP8266 |
| `host` | none | all | none | — | — | — |

## 5. Validation

One loader and validator, `hub/registry.py`. The hub runs it at start; `python -m tools.registry check` runs the
same code in CI. Each error is one line naming the file and the field, for example
`registry/boards/uno-1.json: placements[0].pins.data: D0 is reserved (serial)`. Any error fails the run.

### 5.1 Structure

- `schema: 1`; unknown keys are refused, so a typo fails instead of being ignored.
- Ids are unique within their kind; every reference resolves (part, indicator, node, rail, pin label).
- Each indicator has one unit; every output's `ind` exists and is not `derived`.
- A node belongs to exactly one board or to `core.json`. Its id matches `^[a-z]+-[0-9]+$` and is at most 15
  characters (`HabitatNode` keeps 16 bytes, and `habitat/v1/status/` plus the id fits its 40-byte topic buffers).
- **One producer per (node, indicator):** two enabled placements may not send the same indicator for the same node.
  Otherwise two series would interleave under one node (§11.1: the DHT11 and the SCD41 both measure temperature).
- A placement's `outputs` is a subset of its part's outputs; a placement's `params` are within the part's limits.
- A flag with `needs` (the MAX30102's `motion`, §12) requires an enabled placement on the same board that outputs
  the needed indicator; otherwise the flag could never be raised.
- At most one `active` serial board, because `RigLink` reads one port (§6.5).

### 5.2 Pins, buses and levels

- The pin label exists on that MCU and is not reserved; its kind fits the role (an `analog` role needs an analog pin).
- No two placements share a pin, even when one is disabled, so a disabled part keeps its pins reserved. The
  exception is an I2C bus: I2C parts share the MCU's SDA and SCL.
- I2C addresses are unique on a bus; the bus runs at the lowest `max_hz` of its parts.

### 5.3 Rates and resources

- `period_ms` is within the part's limits.
- Serial boards: the sum over enabled outputs of (1000 / `period_ms`) × 140 bytes × 10 bits stays at or under 50 %
  of the baud rate. At 250000 baud that is 89 lines per second; an HX711 at 80 SPS alone uses most of it.
- MQTT nodes: at most 10 messages per second per node (team value: the 32-slot ring then holds at least 3 s of a
  reconnect).
- RAM and flash are not estimated by the validator; the CI compile measures them (§10).

### 5.4 Safety rules (hard failures)

| Rule | Check | From |
|---|---|---|
| S1 Nothing on the Pi header | a `host` board has no placements | D40 §2 |
| S2 One power source per board | `power.source` takes one value, so "pack and USB" cannot be written as a run configuration. A pack's voltage range (Ni-MH 1.2–1.4 V per cell, alkaline 1.5–1.6 V fresh, times `cells`) must lie inside the MCU's window for `pack.pin`: never 2 cells on VIN, never 3 or more on 3V3, 2 Ni-MH on 3V3 too low. One `chemistry` per pack. `size: "CR2032"` is refused on any board with Wi-Fi | D40 §6 |
| S3 Mercury | a part with `hazards: ["mercury"]` has `handling: "adults_only"`, and each of its placements has `enclosure: "sealed"` | checklist rule 12 |
| S4 Body contact | a `contact: "body"` part only on a board with `power.source` `usb-bank` or `pack` and an MQTT link; never `usb-host` or `mains`, never a serial board | checklist rules 1, 3 and 6 |
| S5 Supply rail | the placement's `supply` is one of the part's `rails` and exists on the MCU; this is how "the KY-017 stays on 3V3, never VIN" becomes a check | D40 §6 |
| S6 Logic level | the MCU's logic level is inside the part's `io_v`, unless the placement says `level_shifted: true` (a breakout with a level shifter) | §11.1 (BME280 on the 5 V UNO) |

### 5.5 What software cannot check

The validator cannot see a cable. "The pack comes out before USB goes in to flash", "never mix cell charge levels",
the mercury cleanup steps and each part's `wiring_notes` (the MAX30102's 1.8 V pull-up jumper, for one) are written
by `gen` into:

- the board's generated header comment (§7.1);
- a marked board table in `firmware/README.md`;
- a marked "per-board checks" section of `docs/safety-checklist.md`, between `<!-- registry:begin -->` and
  `<!-- registry:end -->`, one row per board with a box to tick.

The hand-written checklist rules stay above that section, unchanged. A person still ticks the rows.

## 6. Hub

### 6.1 Loading

`hub/registry.py` reads `registry/` (or `HUB_REGISTRY_DIR`), validates it (§5) and returns a frozen `Registry`.
An invalid registry stops the hub at start with the error list; the hub never runs half-registered. At start the
hub logs the registry hash: SHA-256 of the canonical JSON of all files, sorted by path.

### 6.2 `hub/contract.py`

Every public name stays: `INDICATORS`, `DERIVED`, `CABIN_INDS`, `BODY_INDS`, `INTAKE_ORDER`, `INTAKE_INDS`,
`INTAKE_UNITS`, `INTAKE_CEILINGS`, `BODY_MASS_RANGE`, `NODES`, `SOURCES`, `DEVICES`, `FLAGS`, `CREWS`,
`SYMPTOM_CODES`, `REP_SOURCES`, `EXERCISES`. They are built from the registry when the module is imported, so
`assess`, `api`, `store`, `linksim`, the console's payloads and the existing tests do not change. `parse_reading`
checks `reject_outside` from the registry instead of the two hard-coded ranges. Tests can build a `Registry` from
a temporary folder.

`QUIET_INDS` (`ingest.py`), `UNGATED_INDS` (`assess.py`) and the derive trigger read the `quiet`, `assess` and
`derived` fields (§4.2).

### 6.3 A reading must match a placement

On the channels fed by hardware (`mqtt`, `serial`: the `NODE_CHANNELS` split of D42), a reading is accepted only
when its node's board has an enabled placement of part `dev` with `ind` among its outputs. Otherwise it is rejected
with a new reason code, `unexpected_output`, logged like every reject. This catches `cabin-1` sending `tilt`, or a
stale build sending a channel that the registry has switched off. Software producers (`http`, `internal`, replay
files) are not checked against placements.

### 6.4 Commands

A command goes to the board with a placement, enabled or not, whose part serves it: `alarm` goes to `uno-1`,
because its `buzzer-passive` placement lists `alarm`, and so over serial. `servo`, `cal` and `tare` also go to
`uno-1` through its disabled `servo` and `HX711` placements, and the firmware answers `not_built` as today. A
command that no placement serves is dropped by the hub with a log line. This replaces `SERIAL_NODES` and the node
mapping in `command_topic()`; the gap analysis of 2026-11-15 asked for that mapping to be checked, and this design
does not depend on the answer. The argument rules for each command stay as code in `hub/commands.py`.

### 6.5 Many boards

Any number of MQTT boards work at once: a `boards/cabin-2.json` makes `cabin-2` a known node with no hub code.
There is one serial board, `HUB_SERIAL_BOARD` (default: the one active serial board), because `RigLink` reads one
port; the validator refuses a second active serial board until `RigLink` handles several. Connecting the port marks
all of that board's nodes online or offline together, as today.

### 6.6 API

- `GET /api/registry`: the resolved indicators (label, unit, scope, lane hint), the boards (status, link, power
  source, nodes, placements with part and pins) and the hash. Read-only.
- `GET /api/status`: each `nodes[]` entry gains `board`.

### 6.7 A stale build

Generated firmware prints `# registry=<first 8 hex digits of the hash>` in its banner. For the serial board the hub
compares it with its own hash and logs a WARNING when they differ: the board runs a build older than the registry.
It is a warning only. MQTT nodes print it on their serial console only, because their status payloads and the
contract do not change.

## 7. Firmware

### 7.1 `board_config.h`

`gen` writes one header per sketch, `firmware/<sketch>/board_config.h`:

- one block per board that runs the sketch, selected with `-DBOARD_<ID>` (`-DBOARD_CABIN_2`); with no flag, the
  sketch's `default` board (§4.4; the bench board), so today's plain `arduino-cli compile` commands still work;
- `BOARD_ID`, `REGISTRY_HASH`, `LINK_BAUD`;
- per placement, under the part's macro prefix: `ENABLE_DHT 1`, `PIN_DHT 2`, `DHT_PERIOD_MS 5000`,
  `DHT_NODE "cabin-1"`, `DHT_TYPE DHT11`, and each param as a macro (`TILT_DEBOUNCE_MS 200`). A disabled placement
  gets `ENABLE_HX711 0` and still defines its pins;
- pins as GPIO numbers with the board label in a comment (`#define PIN_TILT 14 // D5`), so the tilt twin's ESP32
  stand-in compiles the same header, where the `D5` macro does not exist;
- a header comment with the board's power rules, wiring notes and hazards (§5.5) and "generated by tools.registry
  from registry/, do not edit";
- every macro inside `#ifndef`. Precedence: the twin's generated `wokwi_twin.h` (from the parts' `twin_defines`),
  then `board_config.h`, then the sketch's own defaults.

### 7.2 One change to each sketch

In `exercise-uno.ino` and `tilt-esp8266.ino`:

- the `static const` pin constants become `#ifndef` defaults with today's values;
- the sketch includes `board_config.h` through `__has_include`, after `wokwi_twin.h`: the same pattern as
  `wokwi_twin.h` and `secrets.h`;
- the node names, the DHT period and the tilt debounce and heartbeat read their macros;
- the sketch calls `partsBegin()` in `setup()` and `partsPoll(now)` in `loop()` (§7.3) and defines `partEmit`.

The parts on the bench today (DHT11, HX711, servo, NTC, KY039, buzzer, KY017) keep their code in the sketch
(`driver: "inline"`), and their behaviour does not change. The archived `vitals-esp32` gets a `board_config.h` but
no code change.

### 7.3 New part types: `firmware/libraries/HabitatParts/`

- One header per part (`SCD41.h`, `BME280.h`) with a pure block (CRC, frame parsing, compensation, flag rules)
  between `BEGIN PURE` and `END PURE`, and a small hardware class: `begin(TwoWire&)`, `poll(now_ms, &sample)`.
- A driver never knows the transport.
- `gen` writes `board_parts.h` per sketch: `partsBegin()` and `partsPoll(now)` for the enabled library parts, which
  call one hook the sketch defines, `partEmit(const PartOut&, float val, uint8_t q)`. `PartOut` is a generated
  constant with the node, the indicator, unit and device (names, and the `ReadingFormat` indexes). On the UNO the
  hook prints a contract line through the existing `emitReading`; on an ESP it calls `node.queue`.
- After that one change, a new library part on an existing board needs no sketch edit.
- `board_parts.h` includes the driver as `"SCD41.h"`: on a real build `arduino-cli` finds it in
  `firmware/libraries`; in a Wokwi project it finds the copy that `sync.sh` puts next to the sketch (§9).

### 7.4 `ReadingFormat`

The `Ind` and `Dev` enums in `ReadingFormat.h` and the name, unit and decimals tables in `ReadingFormat.cpp` are
generated between `// registry:begin` and `// registry:end`. They list every indicator some part file outputs and
every sensor part. The enums are indexes used only on the node (the wire carries names), so their order and length
can change safely. Indicators that no part file outputs (`mood` and `symptom`, for example) leave the firmware
tables, and `RING`, which no firmware sends either, is a `core.json` device.

## 8. Console

- `gen` writes `console/src/generated/registry.ts`: the `Ind` union, `INTAKE_INDS`, and each indicator's label,
  unit, scope and lane hint, plus the `LaneWindow` type from the windows the console supports (`instant`,
  `mean_1h`; the validator accepts only these). `console/src/contract.ts` re-exports `Ind` and `INTAKE_INDS` from
  it, and its hand-written copies go away.
- `LANES` is built from the lane hints, sorted by `order`. The seven reading lanes of today become hints with the
  same label, window and `optional` value. The `work` lane, built from reps, stays in code.
- A new indicator with a lane hint gets a lane. Its bands still come from `/api/thresholds`; with no rule, the lane
  shows values with status "unknown", as lanes do today.
- When more than one node reports an indicator (`cabin-1`, `cabin-2`), its lane draws one series per node, with the
  node id in the legend.
- Lanes come from the generated file, not from `/api/registry`, so the offline replay build on Vercel keeps
  working. The status view groups nodes by board, from `/api/registry` when the hub answers and from the generated
  file when it does not.
- Panel cards, the history special views, `copy.ts` texts and the ground page stay hand-built. A new indicator
  appears there only when someone adds it.

## 9. Wokwi twins

- Each part's `wokwi` block gives its stand-in part (or custom chip), its label and its role → part pin map. A part
  Wokwi does not have names a custom chip in `firmware/wokwi/parts/` (`scd41.chip.c`), as the vitals twin already
  does for the MAX30102 and MLX90614.
- `check` reads every board's twins' `diagram.json`:
  - every enabled placement is drawn with its stand-in, labelled, and wired from the right MCU pin (the tool has a
    pin-name table for `wokwi-arduino-uno` and `wokwi-esp32-devkit-v1`);
  - no disabled placement is wired to the MCU;
  - the existing full-bench rules hold (the UNO is the first microcontroller; the Pi header is unwired).
- `gen` writes each twin's `wokwi_twin.h`, and the band table of `firmware/wokwi/full-bench/rpi3-hub.chip.c`
  between markers, from the `instant` rules in `data/thresholds.json` for the cabin indicators the serial board
  outputs. The chip cannot judge 1-hour or 7-day means, so ppCO2 is not judged there. The existing "chip bands
  equal the thresholds file" test stays as the check.
- `diagram.json` stays hand-laid-out and pasted into the saved projects by hand. `sync.sh` and `check_sync.sh`
  also copy and check `board_config.h`, `board_parts.h` and the `HabitatParts` headers a twin needs.

## 10. Tests and CI

Tests loop over the registry; no test code is generated.

| Test | Checks |
|---|---|
| `hub/tests/test_registry.py` | one failing case per validator rule in §5, including S1–S6, each on a small registry in a temporary folder; the real registry passes |
| `hub/tests/test_registry_gen.py` | `gen --check` finds no stale generated file; it replaces the `ReadingFormat` substring checks in `test_contract.py` and `test_firmware_tilt.py` |
| `hub/tests/test_registry_outputs.py` | for every enabled output, a synthetic contract line at mid-range is stored on its board's channel; the same line from another node, or for a disabled placement, gets `unexpected_output` |
| `hub/tests/test_registry_twins.py` | the diagram checks of §9 |
| `hub/tests/test_registry_migration.py` | the tables built from the registry equal a snapshot of today's hard-coded tables (taken in the first PR); every line in `data/replay/*.jsonl` still parses as before; `reading_to_dict` output is unchanged |
| `console/tests/registry-lanes.test.ts` | an extra indicator with a lane hint gives an extra lane; two nodes give two series; today's seven lanes are unchanged |
| `firmware/libraries/HabitatParts/test/test_*.cpp` | each driver's pure block, run by the CI step that already runs every library `test/test_*.cpp` |

CI (`.github/workflows/ci.yml`):

- `python -m tools.registry check`;
- `python -m tools.registry builds` prints one `arduino-cli compile` per active and archived board (with its
  `-DBOARD_<ID>` flag and `--libraries firmware/libraries`), plus an "every placement enabled" build per board; the
  compile step runs that list instead of today's hand-written commands. That adds the archived `vitals-esp32`
  sketch, which CI runs host tests for today but does not compile;
- a RAM gate from the compile output: each board's real configuration at most 75 % of the MCU's RAM, each "every
  placement enabled" build at most 90 %. Measured on 2026-11-15 with `arduino-cli`: the UNO sketch uses 961 bytes
  (46 %) with the D40 defaults and 1,272 bytes (62 %) with every flag on.

## 11. Worked example: CO2 and pressure on the UNO

The bench has no CO2 or pressure source today (D40 §3, §9). D45 (signals) uses them "when a source exists"; this is
that source.

### 11.1 Why two parts

`hub/derive.py` computes `cabin_ppco2` from `cabin_co2` and the newest good `cabin_p` within 60 s. With no
`cabin_p` it uses 1013.25 hPa and adds `assumed_pressure`, and `hub/assess.py` judges only readings whose flags are
exactly `["ok"]`. So an SCD41 alone would put ppCO2 on the console but never judge it against NASA-STD-3001
(`co2_1h`, `co2_7d`). A BME280 on the same bus supplies `cabin_p` and makes it judged. The example also shows two
parts sharing one I2C bus. Its pressure period is 30 s, so a good pressure reading is inside the 60 s window even
after one failed read.

### 11.2 Part files

`registry/parts/SCD41.json`:

```json
{ "schema": 1, "id": "SCD41", "kind": "sensor", "src": "hobby", "driver": "SCD41", "macro": "SCD41",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x62", "max_hz": 400000 },
  "supply_v": [2.4, 5.5], "rails": ["5V", "3V3"], "io_v": [2.4, 5.5], "contact": "none", "hazards": [],
  "outputs": [
    { "ind": "cabin_co2",  "range": [0, 5000], "flags": ["settling", "out_of_range", "no_contact"] },
    { "ind": "cabin_temp", "range": [-10, 60], "flags": ["no_contact"] },
    { "ind": "cabin_rh",   "range": [0, 100],  "flags": ["no_contact"] }],
  "period_ms": { "min": 5000, "default": 5000 },
  "params": { "settle_s": { "min": 0, "max": 600, "default": 60 },
              "fails_for_no_contact": { "min": 1, "max": 10, "default": 3 } },
  "wokwi": { "chip": "scd41", "label": "SCD41 CO2 sensor (simulated chip)", "pins": { "sda": "SDA", "scl": "SCL" } },
  "note": "Flags as nodes/cabin_pi: settling for 60 s after measurement starts, out_of_range above 5000 ppm." }
```

`registry/parts/BME280.json` has `i2c { "addr": "0x76", "max_hz": 400000 }`, `supply_v [1.71, 3.6]`,
`rails ["3V3"]`, `io_v [1.2, 3.6]`,
outputs `cabin_p` (range [300, 1100], flags `settling` on the first reading, `no_contact`), `cabin_temp` and
`cabin_rh`, `period_ms { "min": 1000, "default": 30000 }`, and the wiring note "a bare BME280 module is 3.3 V only:
on the 5 V UNO use a breakout with a regulator and a level shifter". Both files already exist as Python drivers in
`nodes/cabin_pi/` (`scd41.py`, `bme280.py`), retired by D40 because nothing goes on the Pi header.

### 11.3 Placements on `uno-1`

```json
{ "part": "SCD41", "node": "cabin-1", "pins": { "sda": "A4", "scl": "A5" }, "outputs": ["cabin_co2"],
  "period_ms": 5000, "supply": "5V" },
{ "part": "BME280", "node": "cabin-1", "pins": { "sda": "A4", "scl": "A5" }, "outputs": ["cabin_p"],
  "period_ms": 30000, "supply": "3V3", "level_shifted": true }
```

Both pick one output each, because the DHT11 already sends `cabin_temp` and `cabin_rh` for `cabin-1` (one producer
per node and indicator, §5.1). The owner can later move temperature and humidity to the BME280 by switching the
outputs and disabling the DHT11; the console and hub need nothing for that either.

### 11.4 What `check` says

- A4 and A5 are the UNO's I2C pins; both parts share them; `0x62` and `0x76` differ; the bus runs at 400 kHz.
- S5: the SCD41 on `5V` and the BME280 on `3V3` are rails each part allows. S6: the UNO's 5 V logic is outside the
  BME280's `io_v`, and the placement says `level_shifted: true`, so it passes; without it, the check fails.
- Serial load: DHT11 0.4 lines/s, SCD41 0.2, BME280 0.03, about 0.63 lines/s in all, far under 89.
- No hazard and no body contact.

### 11.5 What `gen` changes

- `firmware/exercise-uno/board_config.h`: `ENABLE_SCD41 1`, `SCD41_NODE "cabin-1"`, `SCD41_PERIOD_MS 5000`,
  `SCD41_SETTLE_S 60`, `ENABLE_BME280 1`, `BME280_PERIOD_MS 30000`, `I2C_HZ 400000`, and a new `REGISTRY_HASH`.
- `firmware/exercise-uno/board_parts.h`: `Wire.begin()`, `Wire.setClock(I2C_HZ)`, the two drivers' `begin` and
  `poll` calls, and their `partEmit` calls for `cabin_co2` (dev `SCD41`) and `cabin_p` (dev `BME280`).
- The README board table and the safety section gain the BME280 wiring note.
- The UNO's banner gains `# registry=…`; the `# channels` line lists `scd41=on bme280=on`.
- The operator reflashes the UNO. Nothing else on the bench changes.

### 11.6 Drivers

- `HabitatParts/SCD41.h` ports `nodes/cabin_pi/scd41.py`: the same commands (`0x21B1` start periodic,
  `0xE4B8` data ready, `0xEC05` read, `0x3F86` stop), the same CRC-8 (polynomial 0x31, init 0xFF) and the same test
  vector (`0xBE 0xEF` gives `0x92`, from the Sensirion datasheet, already in `nodes/cabin_pi/tests`). Host tests:
  CRC, frame parse with a bad CRC, settling for the first 60 s, `out_of_range` above 5000, `no_contact` after three
  failed reads.
- `HabitatParts/BME280.h` ports `nodes/cabin_pi/bme280.py`, with the datasheet's 32-bit integer compensation, so the
  AVR needs no 64-bit or double maths. Host tests use the calibration words of the Python fakes
  (`nodes/cabin_pi/tests/fakes.py`) and agree with the Python driver within 0.1 hPa.

### 11.7 Hub, console and Wokwi

- Hub: no code. `cabin_co2` and `cabin_p` already exist; `cabin_ppco2` is derived; `co2_1h` and `co2_7d` exist;
  the new placements make `cabin-1` readings with dev `SCD41` and `BME280` pass §6.3.
- Console: no code. The `cabin_p` and `cabin_ppco2` lanes exist as optional lanes and appear when data arrives.
- Wokwi: a custom chip `firmware/wokwi/parts/scd41.chip.c` (I2C at 0x62, answers the four commands with CRC, a `co2`
  control) with native tests like the vitals chips. A second chip, `bme280.chip.c` (I2C at 0x76), answers with the
  calibration and raw words of `nodes/cabin_pi/tests/fakes.py`, so it proves the wiring and the driver path at one
  fixed pressure; the host tests cover the compensation maths. Both are drawn on `uno-rig` and `full-bench`, and
  `check` verifies the A4/A5 wiring.
- Tests: `test_registry_outputs.py` covers `cabin-1`/`cabin_co2`/`SCD41` and `cabin-1`/`cabin_p`/`BME280` with no
  new test code.
- RAM: the AVR `Wire` library adds its buffers, and the two drivers a few dozen bytes. The CI gate of §10 measures
  the result; the estimate is about 60 % for the real configuration.

## 12. Worked example: the archived vitals node, in short

`registry/boards/vitals-1.json`: `status: "archived"`, `mcu: "esp8266"`, `fqbn: "esp8266:esp8266:nodemcuv2"`,
`sketch: "firmware/vitals-esp32"`, `twins: ["firmware/wokwi/vitals-esp32"]`, `link: { "transport": "mqtt" }`,
`power: { "source": "usb-bank" }`, node `vitals-1`. Archived means validated and compiled in CI, not on the bench.

| Part | I2C | `contact` | Outputs on `vitals-1` | Period | Notes |
|---|---|---|---|---|---|
| `MAX30102` | 0x57, 400 kHz | `body` | `hr`, `spo2`, flags `no_contact`, `settling`, `motion` with `needs: { "motion": "motion" }` | 1 s (hr), 4 s (spo2) | rails `3V3`; wiring note: many boards pull SDA/SCL up to 1.8 V, move the jumper to 3.3 V |
| `MLX90614` | 0x5A, 100 kHz (SMBus) | `body` | `skin_temp`, flags `no_contact`, `settling` | 2 s | non-contact, but worn on the body |
| `MPU6050` | 0x68, 400 kHz | `body` | `motion` | 1 s | supplies the motion flag for the MAX30102 |

What the design exercises:

- three parts on one bus: addresses differ, and the bus runs at 100 kHz, the MLX90614's limit, which is what
  `firmware/README.md` already says by hand;
- a flag from one part on another part's reading: `check` fails if `vitals-1` has a MAX30102 that raises `motion`
  and no enabled placement outputs `motion`;
- S4: the board passes because a protected power bank is `usb-bank` and the link is MQTT. The same parts on
  `uno-1` (serial, `usb-host`) fail S4, which is checklist rules 1 and 3 as a check;
- the ESP8266's boot pins D3, D4 and D8 stay free (§4.5); I2C is on D1 and D2;
- rate: 1 + 0.25 + 0.5 + 1 = 2.75 messages per second, under 10;
- the cross-part motion logic stays in the archived sketch (`driver: "inline"`); the descriptor only declares the
  dependency.

## 13. Rollout (after judging)

Nothing changes in the submitted build. Each step gets its own implementation plan and its own PR with CI green.

1. **Registry and hub tables.** `registry/` with every file of today's bench, archive and core; `hub/registry.py`;
   `contract.py`, `ingest.py`, `assess.py` built from it; `test_registry.py` and the migration snapshot. No behaviour
   change: the full pytest suite and the snapshot are the gate.
2. **Generation.** `tools/registry` with `check`, `gen` and `builds`; generated `ReadingFormat` blocks,
   `registry.ts`, `wokwi_twin.h`, `board_config.h`, the README and checklist sections; the one-time sketch change
   (§7.2) and `sync.sh` updates; CI steps of §10. The operator reflashes the UNO and the NodeMCU; the bench check is
   that their lines are the same as before apart from the new `# registry=` banner line.
3. **Hub behaviour.** `unexpected_output`, command routing by board, `/api/registry`, `board` in `/api/status`, the
   banner hash warning, the console's generated lanes and per-node series.
4. **New parts.** `HabitatParts` with the SCD41 and BME280 drivers, the Wokwi chip(s), the two placements of §11.3.
   The operator buys and wires the parts and reflashes; the bench check is a `cabin_ppco2` reading judged by
   `co2_1h` on the console.

## 14. Out of scope

- A node announcing its own descriptor at run time, and any run-time pin or rate configuration (Q2, Q3).
- More than one serial board (§6.5).
- Generating or re-laying-out `diagram.json`.
- Lanes on the ground page, panel cards and `copy.ts` texts for new indicators.
- A new kind of command without code.
- Any change to contract v1, to `data/thresholds.json` sources, or to the camera's reps.
- Removing the archived sketches and twins.
