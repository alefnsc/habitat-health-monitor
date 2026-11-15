# Validation

## Offline check

Dry run, Sat 2026-11-14 (C agent). The uplink was not physically unplugged and no camera was attached, so the
hotspot and camera-set parts of the acceptance still have to be done by a person.

- Static scan: the built `console/dist` and `camera/dist` contain no host outside the fixed lists in
  `console/tests/offline.test.ts` and `camera/tests/offline.test.ts`. No web font, no external script or stylesheet.
  A planted external script tag made the camera test fail, then it was removed.
- Bench check 1 (dry run): hub on localhost:8000 serving `/` and `/camera/`. Every console screen opened
  (status, entry, history, exercise, food, nasa, prompts, body). The browser's resource list held one origin only,
  `http://localhost:8000`, for the console and for the camera page. Exercise showed "HTTP 404" (sessions routes not on the
  hub yet) and NASA showed "NASA data not available on this hub".
- Bench check 2 (dry run): hub stopped for about 10 s. The "Hub connection lost" banner appeared within 8 s. After the hub
  restarted the banner cleared and the board refilled without a reload.
- Not yet done: camera preview and a camera set with the uplink off; re-check at the 16:00 freeze.

## Full-stack check (synthetic)

Run by the H agent, Sat 2026-11-14 11:12 local, on one machine with `scripts/dev-up.sh`: hub with all features, `DONKI_MODE=replay`, no broker, link simulator on `linksim/link.demo.json`, ground receiver, and `sim-1` replaying `data/replay/l0-synthetic.jsonl` over HTTP (`python -m hub.sim --http`, 5040 messages, backdated). All data is synthetic or a committed snapshot; no hardware and no network.

| Screen / path | Endpoint | Result |
|---|---|---|
| Status board | `GET /api/status` | 200, one worst-of entry per indicator (hr, cabin_*, cabin_ppco2 with sources) |
| History | `GET /api/readings?ind=cabin_ppco2` | 200, replayed rows (node `sim-1`, src `replay`) |
| Exercise | `POST /api/sessions`, camera reps via `POST /api/reps`, `GET /api/reps?session=`, end, `GET /api/sessions` | 200/201; two camera reps paired, `camera_reps` 2 |
| Food | `GET /api/food/catalog`, `POST /api/food/log`, `GET /api/food/day` | 200/201; one meal gave a kcal total (food routes and `app.state.food` wired) |
| NASA | `GET /api/nasa/space-weather` (replay: act), `POST .../ack`, `GET /api/nasa/iss-reference` | 200 |
| Prompts | `GET /api/prompts`, `POST /api/prompts/{id}/answer` | cabin_trigger prompt appeared from the `co2_1h` alert; answer stored a `symptom` reading |
| Link | `GET /api/link` | 200; demo config reached `blackout` |
| Push | `WS /ws` | `snapshot` frame on connect |
| Outbox to ground | `GET /api/outbox` via linksim to receiver | receiver `/ground/summary`: 5765 stored, 0 missing ids |

Not working in this run (not hub-side wiring faults):
- `GET /api/nasa/iss-cabin` 404: `hub.nasa.isslive` and `hub.nasa.isslive_client` are not on main, so the `iss` feature is skipped.
- `GET /api/exercise/day` 404: the route is not implemented on main.
- `GET /api/food/references` 503: `data/food/references.json` does not exist.
- `hub.mcp_server` and `hub.wearable` are not on main, so those features are skipped (logged at start).
- `nodes` in `/api/status` is empty because the replay used HTTP, not MQTT. The MQTT path was checked separately against a live Mosquitto.
- `/` and `/camera/` answer 503 until the console and camera builds exist.

## Bench defect 2026-11-15: repeated tilt-1 boot numbers

Found by the read-only bench validation of Sun 2026-11-15 (report kept beside the repository checkout:
`../validacao-2026-11-15/relatorio-sensores-painel.md`, §7 gap 1; evidence `evidence/verify3-mqtt-live2.txt` and
`evidence/check2-hub-tilt.json`). The tilt node's boot numbers ran 4, 7, 9, 8, 10, 11, 1, 2 within one hour. At
14:17:35 UTC four valid readings (boot 9, seq 1 to 4) collided with rows of the same key from 13:33 and were dropped
with no log line, no outbox item and no assessment, a 64.5 s hole in the series.

Fix (decision D42, `docs/decisions/2026-11-15-boot-counter-and-reading-key-design.md`): the ESP8266 boot number
is kept as an append-only flash log instead of the EEPROM emulation's erase-then-write per boot
(`firmware/libraries/HabitatNode/src/BootLog.h`), and the hub stores a repeated key that carries a different sample
under a `clash` number, logs it and counts it per node, while retries of the same sample still dedupe.

Checked on 2026-11-15 without a board and without touching the bench: `pytest -q` (repository venv, live-broker test
excluded), `ruff check`, `firmware/tilt-esp8266/test/run_host_tests.sh` (debounce, heartbeat, serial line and the boot
log against a NOR flash model with torn and refused writes), `arduino-cli compile` for the NodeMCU and for the ESP32
stand-in. Not done: flashing the NodeMCU (operator only) and a bench re-run; the first boot after flashing is 2 and
repeats numbers already stored, which the hub now keeps as `clash` rows with a warning each.
