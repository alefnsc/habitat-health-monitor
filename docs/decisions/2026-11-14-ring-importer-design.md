# Wearable ring importer — design (D41)

Status: approved by the team owner, 2026-11-14 ~15:00. It is the "next step" that D40 §9 left out of scope.

## 1. Goal

The team owner's own sleep-tracking ring gives the hub three body readings: `hr`, `spo2` (nightly) and `sleep_h`.
They arrive as contract-v1 readings through `POST /api/readings`, the same door every node uses. The habitat core
still runs offline. Ring vitals are a **delayed cloud sync**, shown with their true age and never called "live".

## 2. Facts from the vendor's public v2 docs (read 2026-11-14, OpenAPI 1.43)

- Authorization: OAuth2 authorization code, with PKCE `S256` (recommended). The token endpoint takes a form body
  (client id and secret in the body or by HTTP Basic). Refresh tokens are **single-use**: each refresh returns a new
  one. Personal access tokens were deprecated in December 2025 and can no longer be used.
- Scopes used: `heartrate` (heart-rate time series), `spo2` (nightly SpO2 average) and `daily` (sleep documents).
- Endpoints, all `GET` under `/v2/usercollection/`, paged with `next_token`:
  - `heartrate?start_datetime&end_datetime`: rows `{timestamp, timestamp_unix (ms), bpm, source}`, where `source`
    is one of `awake`, `workout`, `rest`, `sleep`, `live` or `session`;
  - `daily_spo2?start_date&end_date`: `{id, day, spo2_percentage: {average} | null, breathing_disturbance_index}`;
  - `sleep?start_date&end_date`: `{id, day, bedtime_start, bedtime_end, total_sleep_duration (s) | null, type}`,
    where `type` is one of `deleted`, `sleep`, `long_sleep`, `late_nap` or `rest`.
- Temperature exists only as `temperature_deviation` (readiness), never as an absolute value. That is why
  `skin_temp` is **not** mapped.
- Every request must send a `User-Agent`. An unapproved app is limited to 10 users, which is enough for one.

The vendor's name and URLs are written only in `DATA_SOURCES.md`. The code reads its URLs from the environment.

## 3. Layout

A separate process, `nodes/ring/`, run as `python -m nodes.ring {auth,pull,replay}`. The hub never calls the cloud.
Two alternatives were rejected: a hub feature that polls the cloud would put a cloud dependency inside the offline
core, and writing to SQLite directly would skip contract validation.

| File | Does | Network |
|---|---|---|
| `mapper.py` | Pure: one *pull record* (raw vendor JSON plus `pulled_at`) → contract-v1 dicts and a skip summary | none |
| `client.py` | Fetches the three endpoints, follows `next_token`, refreshes the token once on a 401 | vendor API |
| `auth.py` | Authorization code with `state` and PKCE; the callback lands on a one-shot `127.0.0.1` server, or the team owner pastes the redirect URL; writes the token file with mode 600 | vendor OAuth |
| `__main__.py` | `pull`: fetch → append the raw record to `var/ring/pulls.jsonl` → map → post. `replay FILE`: map → post | hub only for replay |

Configuration lives in `.env`, which is git-ignored: `RING_API_BASE`, `RING_AUTHORIZE_URL`, `RING_TOKEN_URL`,
`RING_CLIENT_ID`, `RING_CLIENT_SECRET` and `RING_REDIRECT_URI`. The token is `var/ring/token.json` (mode 600) and
the pulls are `var/ring/pulls.jsonl`. Both are under `var/`, which is git-ignored.

## 4. Mapping rules

| Reading | From | Rule |
|---|---|---|
| `hr` (bpm) | heart-rate rows | Only `source` `rest` or `sleep`, because the hub's HR bands are resting bands. Every other row is skipped and counted |
| `spo2` (%) | `daily_spo2.spo2_percentage.average` | Timed at the `bedtime_end` of the `long_sleep` with the same `day`. Skipped when the average is null or there is no such night |
| `sleep_h` (h) | `sleep` with `type` `long_sleep` | `total_sleep_duration / 3600`, rounded to 2 decimals, timed at `bedtime_end`. Naps, rests and deleted periods are skipped |
| `skin_temp` | — | Never emitted |

Every reading has `v 1`, `node ring-1`, `dev RING`, `crew crew-b` and `q ["ok"]`. It gets `["out_of_range"]`
outside 20–250 bpm, 50–100 % or 0–24 h.

| Mode | `src` | `boot` | `age_ms` |
|---|---|---|---|
| `pull` | `hobby` | 1 | `now − sample time`: its true age |
| `replay` | `replay` | 2 | `pulled_at − sample time`: the age it had when it was recorded |

- `seq = epoch_seconds × 4 + k`, with `k` = 1 for `hr`, 2 for `spo2` and 3 for `sleep_h`. The hub dedupes on
  `(node, boot, seq)`, so pulling the same window again is a no-op.
- Separate boots mean a replay can never hide a later real import.
- A night whose SpO2 average the vendor recomputes later keeps the first value the hub received.
- Readings are posted oldest first, so status changes (and so alerts) follow measured time.

## 5. Contract and mirrors

- `hub/contract.py`: `ring-1` is added to `NODES`, and `RING` to `DEVICES`.
- `firmware/libraries/HabitatNode/src/ReadingFormat.h` and `.cpp`: `DEV_RING` and `"RING"` are added before
  `DEV_COUNT`. Firmware never sends `RING`; the table is kept in step with the contract.
- `console/src/copy.ts`: the device label is "Ring (delayed cloud sync)". The SpO2 tile title changes from "SpO2
  (finger sensor)" to "SpO2": since D40 there is no finger sensor, and each tile already shows its device badge.
- The older lane-N wearable *baseline* package (`hub.wearable`, a `baseline_daily` table, plan D12) was optional,
  was cut, and is not built here. The hub's `wearable` feature flag stays a no-op, because the module is absent.
- `crew-b` is already in every mirror. It stays out of `PUBLIC_CREWS` until the team owner signs consent.
  linksim is unchanged: body readings reach the public side only for crews in `PUBLIC_CREWS`.

## 6. The hub with hours-old readings (checked, no change)

- `Store.insert_reading` sets `measured_at = received_at − age_ms`.
- `Assessor.assess` evaluates each rule at `measured_at`. The HR and SpO2 rules and `sleep_night` are `instant`;
  `sleep_week` is a 7-day mean over `measured_at`.
- Alerts fire when a status changes. The order is insertion order, which is why the importer posts oldest first.
  An alert carries the reading's old `measured_at`.
- The buzzer is driven only by the space-weather actuator, so a body alert never sounds it.
- HTTP posts do not touch the node registry, so `ring-1` never shows as an "online" node.

A hub test pins this down.

## 7. Honesty and privacy

- A pulled reading shows as "Hobby sensor · Ring (delayed cloud sync) · 7 h ago". A replayed one shows as
  "Replay (recorded)".
- The committed fixture is a **synthetic** night in the vendor's format, and its header line says so. Real pulls are
  never committed.
- The importer reads only the team owner's account and always tags `crew-b`. No one else's data goes through it, and
  never a minor's.
- No company name appears in code, tests or docs. The vendor is named only in `DATA_SOURCES.md`.
- Hobby values are estimates. Nothing here is a medical device.

## 8. Testing

- Mapper: the HR source filter; SpO2 joined to its night; `long_sleep` only; `skin_temp` never; `age_ms` and `src`
  per mode; deterministic `boot` and `seq`; out-of-range flags; every output passes `parse_reading`.
- Client (respx): `next_token` paging, one refresh on a 401 with the new refresh token saved, the `User-Agent` sent.
- Auth (respx): PKCE challenge, a `state` mismatch rejected, the code exchange form, token file mode 600.
- Replay: the fixture → the FastAPI test client, with no network → readings stored with `src replay`.
- Hub: a reading 6 hours old is assessed at its measured time and its alert carries the old `measured_at`.
- Contract: `ring-1` and `RING` are present, and the firmware device table lists `RING`.
- Gates: `pytest -q`, `ruff check .` and the camera and console tests.
