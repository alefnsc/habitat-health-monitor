# Habitat Health Monitor

## What it is

A crew-facing health monitor for a space habitat that keeps working with no link to Earth. Real sensor circuits (an Arduino UNO and a NodeMCU) feed a local hub. The hub checks every reading against a stated source: NASA-STD-3001 for the cabin and radiation, and labelled clinical references (not NASA-published) for vital signs. It then tells the astronaut what to do and whom to tell, and syncs to a public "ground segment" page over a simulated Mars link with light-time delay and blackouts.

Built during the NASA Space Apps Challenge 2026 (challenge: *Create Health Monitoring Software for Astronauts on Space Missions*).

## Not a medical device

Hobby-sensor values are labelled estimates. The software never diagnoses and never gives treatment doses. Vital-sign bands are labelled "not NASA-published".

## Quick start (hub)

Needs Python 3.12 and Mosquitto 2.x.

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Broker (macOS: `brew install mosquitto`; Raspberry Pi: `sudo apt install -y mosquitto mosquitto-clients`):

```bash
mkdir -p var
mosquitto_passwd -c hub/mosquitto/passwd habitat
mosquitto -c hub/mosquitto/habitat.conf -v
```

Copy `.env.example` to `.env` and fill it in locally. Never commit `.env`, the broker password file or any API key.

## Run the hub (development)

1. `mosquitto -c hub/mosquitto/habitat.conf` (create `hub/mosquitto/passwd` first; it is git-ignored)
2. `python -m hub`
3. `python -m hub.sim --file data/replay/l0-synthetic.jsonl --speed 10` (synthetic demo input, not measurements)
4. open `http://<hub-ip>:8000/`

Settings come from `HUB_*` environment variables (see `.env.example`). Without a broker the HTTP API
still serves and the MQTT subscriber keeps retrying.

## Run with Docker

Decision D47 (`docs/decisions/2026-11-15-docker-stack-design.md`). One image, built from the `Dockerfile`, runs
the hub, the link simulator and the local ground receiver; `compose.yaml` adds the Mosquitto broker. You build the
image yourself: nothing is pushed to a registry. Needs Docker with Compose 2.24 or newer. Build from a clean
clone: the image copies `data/` as it is.

1. **Broker password file**, `hub/mosquitto/passwd`. It is git-ignored, mounted read-only and never copied into
   the image. With Mosquitto installed: `mosquitto_passwd -c hub/mosquitto/passwd habitat`. Without it, use the
   broker image (it asks for the password twice):

   ```bash
   docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/hub/mosquitto:/work" eclipse-mosquitto:2 \
     mosquitto_passwd -c /work/passwd habitat
   ```

2. **`.env`**: copy `.env.example` and set `HUB_MQTT_PASS` to the same password. The hub container reads it.
   Compose sets the broker and linksim addresses, the ports, the database path and the page folders itself, so
   the `.env` of a native hub works unchanged.
3. **Start**: `docker compose up -d --build`, then open `http://<host>:8000/`. Logs: `docker compose logs -f hub`.
   Stop: `docker compose down`. `docker compose down -v` also deletes the databases (the `var` volume).

Synthetic demo: `docker compose --profile sim up -d --build` also runs `python -m hub.sim`, which replays
`data/replay/l0-synthetic.jsonl` into the hub as node `sim-1` (synthetic data, not measurements) and exits.

Host ports: hub 8000 and broker 1883 on every interface; linksim 8200 and receiver 8100 on 127.0.0.1 only. When a
native hub or broker already holds them, choose others and a project name of your own:
`HOST_HUB_PORT=18000 HOST_BROKER_PORT=18830 HOST_LINKSIM_PORT=18200 HOST_RECEIVER_PORT=18100 docker compose -p habitat-try up -d`.

**Serial (the UNO on USB).** Linux only, for example the Pi (`docs/pi-setup.md`): set `HUB_SERIAL_PORT` in `.env`
(default `/dev/ttyACM0`) and start `hub-serial` instead of `hub`, by naming the services:

```bash
docker compose --profile serial up -d --build broker hub-serial linksim receiver
```

Never start `hub` and `hub-serial` together: both want port 8000. Docker Desktop on macOS cannot pass a USB
device to a container, so on a Mac run the hub natively for serial (`python -m hub`, with
`HUB_MQTT_HOST=127.0.0.1` and `HUB_LINKSIM_URL=http://127.0.0.1:8200` in `.env`) and the rest in compose:

```bash
LINKSIM_HUB_URL=http://host.docker.internal:8000 docker compose up -d --build broker linksim receiver
```

Public uplink from compose: `docs/deploy-public.md`, step 13.

## Hardware

Wiring maps (DRAFT [confirm: hardware member to review before submission]): the whole bench as one Wokwi canvas in `firmware/wokwi/full-bench/` (link in `docs/decisions/links.md`), the UNO wiring table in `firmware/wokwi/uno-rig/README.md`, and the NodeMCU wiring and power in `firmware/tilt-esp8266/README.md`. There is no separate bill of materials in the repository yet.

Layout: two microcontrollers and a hub (decision D40, [confirm: hardware member to review before submission]).
- **Raspberry Pi 3 Model B** is the hub host (Mosquitto, hub, console), with nothing wired to its header. A laptop runs the hub instead if the Pi is not ready. Setup: `docs/pi-setup.md` (not yet run on hardware).
- **Arduino UNO R3** (the bench board; the ATmega328P side of an UNO+WiFi works the same) is the I/O board. It carries a DHT11 (`cabin-1`: cabin temperature and humidity, hobby estimates) and the alarm buzzer, and talks to the hub over USB serial. On an UNO+WiFi the ESP8266 side is unused. Wokwi twin: `firmware/wokwi/uno-rig/`.
- **NodeMCU (ESP8266)** is the `tilt-1` node: a sealed KY-017 tilt pod on the exercise weight, running on four Ni-MH AA cells (into VIN) and talking over Wi-Fi/MQTT. Wokwi twin, with an ESP32 standing in: `firmware/wokwi/tilt-esp32/`.
- **Wearable ring** (decision D41): the team owner's own sleep-tracking ring gives `hr` (rest and sleep samples), nightly `spo2` and `sleep_h` as node `ring-1`, device `RING`, through `python -m nodes.ring` (`nodes/ring/README.md`). The habitat core runs offline; ring vitals are a **delayed cloud sync**, always shown with their age and never as live. Replays of recorded pulls are labelled "Replay (recorded)". No sensor that touches a person is cabled to anything.
- **The whole bench in one Wokwi project:** https://wokwi.com/projects/480768002795017217. The UNO runs its real sketch there; the tilt node and the Pi hub are labelled drawings, because Wokwi runs one microcontroller per project and has no Pi 3. See `firmware/wokwi/full-bench/`.

## Safety

Everything that touches a person runs on battery only. See `docs/safety-checklist.md`.

## Data sources

See `DATA_SOURCES.md`.

- Consent to publish health readings: docs/consent.md

## Validation

See `docs/validation.md`.

## Prior work

The prior-work library is declared in `docs/decisions/links.md` and used only at its pinned commit.

## Links

See `docs/decisions/links.md`.

- Public ground segment setup: docs/deploy-public.md (consent form: docs/consent.md)

## AI use

DRAFT [confirm: operator and hardware member review this text before submission]

Claude Code (Anthropic) helped plan, research, write code and tests, and draft documents. The team defined the idea and all design decisions, approved every threshold and wording choice, ran all hardware and validation work, and reviewed the outputs. Every AI-assisted commit carries a `Co-Authored-By` trailer. Two presentation images are AI-generated illustrations with a visible label, and the 29-second video's narration is an AI-generated voice (ElevenLabs). One 1-second clip in the video is AI-generated video, labelled on screen. Full disclosure: [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md).

## Licence

Apache-2.0. See `LICENSE`.
