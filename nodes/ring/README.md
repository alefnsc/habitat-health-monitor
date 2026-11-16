# Wearable ring importer (`ring-1`, decision D41)

The team owner's own sleep-tracking ring gives the hub three body readings through the normal
contract-v1 door, `POST /api/readings`:

| Reading | From | Note |
|---|---|---|
| `hr` (bpm) | heart-rate samples tagged rest or sleep | awake, workout, live and session samples are skipped, because the hub's HR bands are resting bands |
| `spo2` (%) | the nightly SpO2 average | timed at the end of that night |
| `sleep_h` (h) | the main sleep period of each night | naps are skipped |

`skin_temp` is not mapped: the ring reports only a temperature *deviation*.

Every reading is node `ring-1`, device `RING` and crew `crew-b`. The vendor and its URLs are listed only in
`DATA_SOURCES.md` ("Wearable ring").

## Honesty

- The habitat core runs offline. This importer is a separate process. Ring vitals are a **delayed cloud sync**: a
  pull is `src hobby` with its **true** age (often hours), shown as "Ring (delayed cloud sync) · 7 h ago", never as
  live.
- A replay of a recorded pull is `src replay`, shown as "Replay (recorded)".
- Hobby values are estimates. This is not a medical device.
- Only the team owner's own account goes through this importer, and never a minor's data. `crew-b` stays out of
  `PUBLIC_CREWS` until a signed consent form exists.

## Commands

Run from the repository root. Settings come from `RING_*` environment variables, or from `.env` for any that are
unset (see `.env.example`).

```bash
python -m nodes.ring replay data/replay/ring-synthetic-nights.jsonl --hub http://127.0.0.1:8000
python -m nodes.ring auth
python -m nodes.ring pull --days 2 --dry-run
python -m nodes.ring pull --days 2 --hub http://127.0.0.1:8000
python -m nodes.ring replay var/ring/pulls.jsonl
```

- `replay` needs no cloud access, only the local hub. `data/replay/ring-synthetic-nights.jsonl` is **synthetic**
  (two invented nights).
- `auth` signs in once (OAuth2 authorization code with PKCE). It writes `var/ring/token.json` with mode 600 and
  refuses to load the file if its mode is anything else.
- `pull` appends the raw cloud answer to `var/ring/pulls.jsonl` (mode 600, git-ignored) **before** mapping it, so
  every real pull can be replayed later. `--dry-run` saves the pull and posts nothing.
- Pulling or replaying the same window twice is harmless: `seq` is fixed per sample and the hub dedupes. Pulls use
  boot 1 and replays boot 2, so a replay never hides a real import.

## One-time setup (team owner only)

1. Register a developer application **for this importer only** on the ring vendor's developer portal (link in
   `DATA_SOURCES.md`). Give it a neutral name, the scopes `daily`, `heartrate` and `spo2`, and exactly **one**
   redirect URI. Set `RING_REDIRECT_URI` to that same value. Use either:
   - `http://localhost:8799/callback`: `auth` listens for the callback itself; or
   - a path on the project's public site that serves a static 404, such as `https://<public site>/ring/callback`.
     `auth` then asks you to paste the address the browser stops on.

   Do not use `127.0.0.1`: the vendor's load balancer answers 403 to any request that carries it. Do not reuse
   another product's app either (decision D41 §9).
2. Copy the client id and secret into `.env`, which is git-ignored, along with the three URLs from
   `DATA_SOURCES.md`. The token URL is the identity server's own endpoint; the older one refuses every exchange.
3. Run `python -m nodes.ring auth --use-registered-redirect`, sign in, and allow `heartrate`, `spo2` and `daily` on
   the consent page.
4. Run `python -m nodes.ring pull --dry-run` and check the counts. Then pull for real with the hub running.

### If sign-in fails

- `auth` asks for the client id (echoed) and the secret (hidden) when `.env` lacks them, and saves them at mode 600.
- `port … is in use`: another program holds the callback port. `auth` stops before the browser opens, so no code
  can reach that program. Register a free port and set `RING_REDIRECT_URI` to match.
- The vendor's page says `400 invalid_request` before sign-in: the redirect URI sent does not match the app's
  registration character for character. With exactly one registered redirect, `auth --use-registered-redirect`
  sends none, and the vendor uses the registered one. The listener still waits on `RING_REDIRECT_URI`, so register
  the same value there.
- The consent page names a different app, or after Allow the browser lands on another service's callback: the
  client id in `.env` belongs to that other app. Register a separate app for this importer, and never point
  another app's redirect at this importer.
- A `403 Forbidden` page from the vendor: the request carried `127.0.0.1`, which the vendor's load balancer blocks.
  Register `localhost` instead (step 1).
- `no redirect within 300 s`: the browser never came back to `RING_REDIRECT_URI`. Run
  `auth --use-registered-redirect --paste` and paste the address the browser ends on. That address holds the code
  even when the page does not load. Paste it into the terminal where `auth` is waiting, and do it quickly: the code
  expires within minutes.
- `token endpoint answered 400: … invalid_request` after the paste: `RING_TOKEN_URL` is the older token URL. Use
  the identity server's token endpoint listed in `DATA_SOURCES.md`.

## Tests

`pytest nodes/ring/tests` covers the mapper, record files, OAuth, the API client and a replay into an in-process
hub. All of them run without network.
