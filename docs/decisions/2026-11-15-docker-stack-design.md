# Docker image and compose stack for the server side — design (D47)

Status: approved by the team owner on 2026-11-15, before any code was written. Built in the same PR. The image
and the stack run on a laptop and in CI; neither has been run on the Pi yet. Educational prototype, not a medical
device.

## 1. Goal

One command brings up the server side (broker, hub, link simulator and local ground receiver) on any machine with
Docker, with the same settings the native run uses. The Pi gets a second way to run the hub that needs no
script, no systemd units and no page copying. CI proves on every change that the stack starts and moves synthetic
data end to end. Nothing changes in the hub, linksim or receiver code, and nothing is pushed to any registry.

## 2. The image (`Dockerfile`)

One image for the three Python programs, in two stages.

- **`web`** on `node:22-slim`: `npm ci` and `npm run build` for `console/` and `camera/`. The build step runs with
  no network. The camera prebuild copies the pinned wasm out of `node_modules` and checks the committed pose
  model's SHA-256, so neither page fetches anything at build time. The console reads `data/thresholds.json` and
  `data/guidance.json`, and the camera page imports `vendor/ground-truth`, so both are copied in. This stage runs
  on the build machine's own platform, because its output is the same static files on every CPU. That keeps
  the arm64 build fast.
- **`runtime`** on `python:3.12-slim`: `pip install --no-cache-dir .` puts `hub*`, `linksim*`, `receiver*` (under
  `ground/`) and `nodes*` into site-packages, with the sources mounted for that step only. `/app` holds `data/`,
  `linksim/*.json` and the two page builds, and `HUB_CONSOLE_DIST` and `HUB_CAMERA_DIST` point at those builds. The
  user is `habitat` (uid 1000), not root. `WORKDIR` is `/app`, `/app/var` is the data volume, and the
  `HEALTHCHECK` asks the hub for `GET /api/status`. The default command is `python -m hub`.

`.dockerignore` keeps `.env`, `var/`, `hub/mosquitto/passwd`, firmware `secrets.h`, `.venv`, every
`node_modules` (`vendor/**` included), the dist folders, `.git` and the worktrees out of the build context. The
image copies `data/` as it is, so build it from a clean clone.

## 3. The stack (`compose.yaml`)

| Service | Process | Port | Notes |
|---|---|---|---|
| `broker` | `eclipse-mosquitto:2` | 1883 | config `hub/mosquitto/compose.conf` (from `habitat.conf`: auth on, persistence) |
| `hub` | `python -m hub` | 8000 | `env_file: .env` (optional), `var` volume |
| `linksim` | `python -m linksim --hub http://hub:8000 --ground http://receiver:8100 --status-host 0.0.0.0 --state /app/var/linksim-state.json` | 8200, 127.0.0.1 | public uplink only from the environment |
| `receiver` | `python -m receiver --db /app/var/ground.db --host 0.0.0.0 --port 8100` | 8100, 127.0.0.1 | the local ground; no page |

- **Broker password.** The operator's own `hub/mosquitto/passwd` is bind-mounted read-only and never baked in. If
  it is missing, compose refuses to start rather than creating a folder in its place. Mosquitto reads the file
  only after it drops to its own user, so a root shell in the broker container first copies the file inside the
  container, owned by that user, with mode 600. Without this step a file made by `mosquitto_passwd` on the host
  (mode 600, the operator's own) cannot be read on Linux. The README and `docs/pi-setup.md` show how to make the
  file with `mosquitto_passwd`, natively or through the broker image.
- **Settings.** The hub reads `.env` like the native hub. These keys are always set by compose, because inside the
  stack the other programs are reached by service name: `HUB_MQTT_HOST=broker`, `HUB_MQTT_PORT`, `HUB_HTTP_HOST=0.0.0.0`,
  `HUB_HTTP_PORT`, `HUB_LINKSIM_URL=http://linksim:8200`, `HUB_DB`, `HUB_LINK_CONFIG`, the two page folders, and
  an empty `HUB_SERIAL_PORT` for `hub`. So the `.env` of a native hub works unchanged.
- **Host ports** are `HOST_HUB_PORT`, `HOST_BROKER_PORT`, `HOST_LINKSIM_PORT` and `HOST_RECEIVER_PORT`, with defaults
  8000, 1883, 8200 and 8100. Only the hub and the broker listen on every interface (phones and the NodeMCU need
  them). The receiver's ingest has no secret on the local network, so it stays on 127.0.0.1, and so does linksim.
- **Public uplink.** `PUBLIC_GROUND_URL`, `PUBLIC_CREWS` (default empty), `PUBLIC_REPS` (default 0),
  `PUBLIC_FLUSH_S` and `GROUND_INGEST_SECRET` reach linksim only from the environment of the `docker compose`
  command (the shell, or `.env`, which Compose reads to fill `${...}`). The consent rules of
  `docs/deploy-public.md` are unchanged: `PUBLIC_CREWS` empty unless every listed crew is an adult with a signed
  consent form, never a minor, and `PUBLIC_REPS=0` when anyone under 18 uses the rig.
- `linksim` does not wait for the hub: it already retries a hub that is away. That lets it run next to a native
  hub (`LINKSIM_HUB_URL=http://host.docker.internal:8000`).

## 4. Profiles

- **`serial`** adds `hub-serial`: the hub with the UNO's serial device passed through (`devices:`),
  `HUB_SERIAL_PORT` (default `/dev/ttyACM0`) and `HUB_SERIAL_BAUD` (default 250000), the `dialout` group, and the
  network name `hub`. Compose profiles can add a service but cannot change one, so the operator starts it instead
  of `hub` by naming the services: `docker compose --profile serial up -d broker hub-serial linksim receiver`.
  Linux hosts only (the Pi). Docker Desktop on macOS has no USB passthrough: there the hub runs natively for
  serial and the broker, linksim and receiver run in compose.
- **`sim`** adds `sim`: `python -m hub.sim --file data/replay/l0-synthetic.jsonl --http http://hub:8000 --speed 60
  --backdate`, once the hub is healthy. This is synthetic data, not measurements, posted as node `sim-1` over
  HTTP, as `scripts/dev-up.sh` does. It exits when the replay ends.

## 5. CI (`.github/workflows/ci.yml`)

- **`docker`** builds the image and makes a throwaway broker password and `.env`, which are gone with the runner.
  It runs `docker compose --profile sim up -d` on ports 18000, 18830, 18200 and 18100, waits until the hub
  (`/api/status`), linksim (`/link/state`) and the receiver (`/ground/summary`) answer, and checks three things:
  `sim-1` readings in the hub, the hub's login at the broker, and items stored at the receiver. Then
  `docker compose down -v`.
- **`docker-arm64`** builds `linux/arm64` for the Raspberry Pi 3 on 64-bit Raspberry Pi OS (QEMU and buildx,
  no push). It then imports every package inside that image. It runs on every change, like the other jobs. The
  web stage runs natively, so emulation covers only the Python stage.
- A pytest (`hub/tests/test_docker_files.py`, plain text parsing, no new dependency) fails when `.dockerignore`
  stops excluding `.env`, `var/` or `hub/mosquitto/passwd`. It also fails when a `python -m <module>` in the
  `Dockerfile` or `compose.yaml` names a module that is not in the repository or not installed by
  `pyproject.toml`.

## 6. What it does not do

- It does not replace the native run. `scripts/dev-up.sh`, `scripts/pi-setup.sh` and the systemd units stay as
  they are. Use one way or the other on a host: the native broker and hub hold the same ports.
- No registry, no published image, no cloud. `vercel.json` and the Pages workflow are untouched.
- It does not build or serve the public ground page (`ground/`), and it does not run the cabin node
  (`nodes/cabin_pi`) or the ring importer (`nodes/ring`).
- Not yet run on a Pi: `docs/pi-setup.md`, "Another way: Docker", is written but unrun.
