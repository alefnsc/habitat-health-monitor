# Boot numbers that repeat — design (D42)

Status: proposed 2026-11-15 from the bench validation of that day; not yet reviewed by the team owner. It changes
firmware that only the operator flashes, so nothing here is on the bench until that happens.

## 1. Goal

A node that forgets its boot number must not cost the hub any reading. The bench showed the opposite: the tilt node's
number went backwards and restarted within an hour, and the hub, which keys readings on `(node, boot, seq)`, treated
four valid readings as repeats and dropped them without a trace.

## 2. Facts from the bench (2026-11-15)

Source: the bench validation report kept beside the repository checkout,
`../validacao-2026-11-15/relatorio-sensores-painel.md` (§4.2, §7 gap 1), with the broker capture
`evidence/verify3-mqtt-live2.txt` and the hub dump `evidence/check2-hub-tilt.json` in its `evidence/` folder.

- `tilt-1` boot numbers stored in order of arrival: 4, 7, 9, 8, 10, 11, 1, 2, all between 13:25 and 14:32 UTC.
- At 14:17:35 UTC the broker carried four readings of boot 9, seq 1 to 4, values 1/0/1/0, `age_ms` 11 025 down to
  5 742. The hub already held boot 9, seq 1 to 25, from 13:33 to 13:35. The four were answered as duplicates:
  no row, no log line, no outbox item, no assessment. The stored series has a 64.5 s hole (14:17:17 to 14:18:21).
- The UNO's counter (EEPROM, `exercise-uno.ino`) went 7, 8, 11, 14 across its resets: never backwards.
- 64 of 64 messages the broker delivered to the hub were stored; the broker logged 0 QoS duplicates. The hub log
  held 0 `reject` lines.

## 3. What the firmware did, and why that produced the pattern

`HabitatNode::beginWith()` already persisted the boot number through the ESP8266 EEPROM emulation (`EEPROM.begin(8)`,
`get`, `+1`, `put`, `commit`, `end`), since the library's first commit. So the node was not missing a counter. The
EEPROM emulation keeps one 4 KB flash sector and `commit()` erases the whole sector and writes it back, once per boot.
Two failure modes follow, and the bench shows both:

- erase done, write lost (power gone, or the write refused): the sector reads blank, the next boot is 1, then 2;
- erase or write refused: the old value stays, so a number is handed out twice (9 at 13:33 and again at 14:17), and
  an unobserved boot in between makes the series look as if it went backwards (9, then 8).

What the hub cannot tell is why the flash operations failed. The node runs on a 4 × Ni-MH pack through the board's
regulator, boots with the radio on, and the same hour shows keepalive timeouts and seven reconnects; a supply that
sags during the erase is the simplest explanation, but it is not measured here. The design therefore does not depend
on the cause: it removes the per-boot erase and makes the hub tolerate a repeat.

## 4. Firmware: the boot number as an append-only flash log

`firmware/libraries/HabitatNode/src/BootLog.h`, used by `bumpBootCounter()` on the ESP8266 (the ESP32 keeps
`Preferences`, whose NVS is journaled):

- the EEPROM sector is a log of 8-byte slots `(n, ~n)`;
- a boot reads the whole log, takes the highest valid number, adds one for itself and one for every non-blank slot
  written after that number, programs the next free slot and reads it back; a write that does not verify is retried
  in the next slot;
- NOR flash programming only clears bits, so nothing is erased until all 512 slots are used; that single erase every
  512 boots is the only moment a power loss can lose the count;
- a torn write (power lost mid-slot) fails the check word and still counts as a boot, so the next number is higher;
- residual: power lost before the first bit was cleared, or a flash that refuses to program at all, repeats a number.
  The hub side below exists for that case;
- the image the old firmware left (the number at offset 0, the rest erased) reads as one torn slot: the first boot
  after flashing is 2, whatever the old count was.

Host tests: `firmware/libraries/HabitatNode/test/test_boot.cpp`, run by the library commands in `firmware/README.md`
and by `firmware/tilt-esp8266/test/run_host_tests.sh`, against a NOR flash model with torn writes, refused writes,
a blank gap, a smaller number after a larger one, a full sector and a refused erase.

The sketch `tilt-esp8266.ino` is unchanged, so the Wokwi twin's byte-for-byte copy still matches. What differs: the
twin runs the sketch in serial-only mode, where `boot` is the constant 1 (no `HabitatNode`, no flash); the hub never
reads that mode, so nothing changes there.

## 5. Hub: a key clash is stored, logged and counted

`hub/store.py`:

- `readings` gains `clash INTEGER NOT NULL DEFAULT 0` and the unique key becomes `(node, boot, seq, clash)` for rows
  that are not derived. Old databases get the column and the rebuilt index on the first open (`_migrate`), once.
- `insert_reading(..., allow_clash=True)`: when the key is taken, the incoming reading is compared with the rows
  that hold it. A retry of the same sample is the duplicate it always was and is dropped. A different sample is
  stored under the next `clash` number (1 for the second life of a key, 2 for the third).
- "Same sample" means the same indicator and value, measured within `RETRY_WINDOW` (10 s). The node re-formats an
  unacknowledged reading with a fresh `age_ms` before resending it, so `received_at` and `age_ms` both change on a
  retry while `measured_at` holds still within network jitter; a repeated boot number needs a reboot first, which
  puts its samples seconds or more apart. This is why the rule reads `measured_at`, not `received_at` or `age_ms`.
  QoS 1 redeliveries by the broker carry the same payload and are dropped by the same rule.
- `clash` is part of `StoredReading` and so of `/api/readings`, the WebSocket frames and the outbox payload (0 for
  nearly every row).

`hub/ingest.py`: only the channels fed by hardware nodes widen the key (`NODE_CHANNELS` = `mqtt`, `serial`). Software
producers (`http` manual entry, `prompt`, `internal` NASA and food readings) choose their keys for idempotency and keep
exact dropping. Every drop now logs `duplicate channel=… node=… boot=… seq=… id=…` at INFO, and every clash logs
`key clash channel=… node=… boot=… seq=… clash=… id=… measured_at=…` at WARNING. `IngestResult.clash` tells callers.

Counters: `nodes[]` in `GET /api/status` gains `duplicates` and `clashes` per node (`NodeRegistry.record`, fed by the
MQTT router and by `RigLink` for the serial nodes); `RigLink.stats()` gains the same two keys, and `stored` now counts
rows written, not lines accepted.

Unchanged: the `reps` key (the camera's `boot` is its page-load time), derived rows (`cabin_ppco2`, unique on
`derived_from`), and the message contract.

## 6. Alternatives not taken

- Bucket the key by `received_at`: splits a late node retry from its first delivery and double-stores it.
- A per-connection nonce: the broker does not pass the publisher's connection to the hub, and HTTP has none.
- Drop the unique index and dedupe in Python only: loses the database-level guard against a second writer.
- LittleFS for the counter: needs a filesystem partition in the board's flash layout chosen at flash time, formats
  itself when the mount fails (count gone), and costs seconds on the first boot. The log needs no partition.
- Keep dropping and only log: the 64.5 s hole would recur on the next repeat, visibly this time but still lost.

## 7. Testing

- `pytest -q` with the repository venv (the live-broker test excluded: it connects to anything on 127.0.0.1:1883).
- `ruff check` and `ruff format --check`.
- `firmware/tilt-esp8266/test/run_host_tests.sh` (pure block and `test_boot`).
- `arduino-cli compile` for `esp8266:esp8266:nodemcuv2` and the `esp32:esp32:esp32` stand-in, with a copy of
  `secrets.example.h` as `secrets.h`.
- Not done: flashing the NodeMCU (operator only), and any check against the live bench hub or broker.

## 8. Rollout

1. The hub picks the change up on restart; the database migrates itself (one index rebuild, idempotent).
2. The operator flashes the NodeMCU with the pack unplugged (`firmware/tilt-esp8266/README.md`). Its first boot is 2
   and the next few numbers repeat ones already in the bench database; the hub stores them with `clash` 1 and a
   warning each, which is the designed behaviour, not a fault.
3. After a recording, `GET /api/status` `nodes[]` and a grep for `key clash` in the hub log show whether any boot
   number repeated; `GET /api/readings?ind=tilt` shows the `clash` column.
