# Docker image and compose stack (D47) Implementation Plan

**Goal:** the server side (broker, hub, link simulator, local ground receiver) runs from one image and one
`compose.yaml`, on a laptop, in CI and on the Pi, with the native run left as it is.

**Spec:** `docs/decisions/2026-11-15-docker-stack-design.md` (D47), approved by the team owner on 2026-11-15.

**Rules for every task:** never touch the live bench (its checkout, its processes, host ports 1883, 8000, 8100 and
8200). Local Docker runs use the project name `habitat-smoke`, host ports 18000, 18830, 18100 and 18200, and
`docker compose down -v` afterwards. Run pytest as `python -m pytest -m 'not broker'`. Never put `.env`, `var/` or
`hub/mosquitto/passwd` into an image or a commit. No new Python dependency.

## Tasks

- [x] **1. Read the real wiring.** `hub/config.py` (every `HUB_*` name), `hub/__main__.py`, `hub/api.py`
  (an empty `HUB_MQTT_HOST` turns the subscriber off), `linksim/__main__.py` (flags, `PUBLIC_*`,
  `GROUND_INGEST_SECRET`; `PUBLIC_REPS` is on only when it is `1`), `ground/receiver/__main__.py`,
  `hub/sim/__main__.py` (`--state` defaults to `.state/`), `scripts/dev-up.sh`, `hub/mosquitto/habitat.conf`.
- [x] **2. `Dockerfile`.** `web` stage on `node:22-slim` at `$BUILDPLATFORM`; builds with `--network=none`.
  `runtime` stage on `python:3.12-slim`: `pip install .` from a build-time mount, `data/`, `linksim/*.json`, the
  two dist folders, user `habitat`, `/app/var` volume, `HEALTHCHECK` on `/api/status`.
  Check: `docker build` passes; the camera prebuild logs `verify-model: pose_landmarker_lite.task ok` with no
  network; the image holds no `.env`, password file, `secrets.h` or source tree.
- [x] **3. `.dockerignore`.** Secrets, local state, environments, build output, unused folders.
- [x] **4. `compose.yaml` and `hub/mosquitto/compose.conf`.** Services `broker`, `hub`, `linksim`, `receiver`;
  profiles `serial` (`hub-serial`) and `sim`; `HOST_*_PORT` for the host side.
  Check: `docker compose config --quiet`. A 600 password file owned by another uid is unreadable to
  Mosquitto 2.1 when bind-mounted directly, and works when copied in by the root shell.
- [x] **5. Wiring test** `hub/tests/test_docker_files.py`. Check: 3 passed.
- [x] **6. Local smoke** on the safe ports. A throwaway `.env` (which also set `HUB_MQTT_HOST=127.0.0.1` and a bad
  `HUB_SERIAL_PORT`, to prove compose's values win) and a throwaway password file, both git-ignored and deleted
  afterwards.
  - `--profile sim`: hub, linksim and receiver healthy. 50 of 50 newest `cabin_temp` readings from `sim-1`. The
    hub logged `mqtt connected to broker:1883` and the broker logged the `habitat` login. The receiver stored
    linksim's items. Console and `/camera/` answer 200.
  - `serial`, with `/dev/null` standing in for the UNO: `hub-serial` got the device, `HUB_SERIAL_PORT`, group
    `dialout` and the name `hub`, and the rig tried the port.
  - `broker linksim receiver` alone, with no image yet: the image is built and linksim waits for an absent hub.
  - Public uplink pointed at the local receiver with a throwaway secret: linksim printed `public uplink ON` and
    `public crews: none; reps public: no`.
- [x] **7. CI.** `docker` job (build, throwaway password and `.env`, `--profile sim up -d`, the three answers,
  `sim-1` readings, broker login, receiver items, `down -v`) and `docker-arm64` job (QEMU, buildx,
  `linux/arm64`, no push, imports every package).
- [x] **8. Docs.** README "Run with Docker"; `docs/pi-setup.md` "Another way: Docker"; `docs/deploy-public.md`
  step 13 (compose linksim with the public uplink, same consent rules).
- [x] **9. Spec and plan** (this file).
- [ ] **10. Draft PR and CI.** Push `feat/docker-stack`, open the draft PR, and wait for every CI job. Fix on the
  branch if one fails, at most three rounds.

## Not in this plan

- Running it on the Pi (`docs/pi-setup.md`, "Another way: Docker", is unrun).
- Any registry, published image or cloud host.
