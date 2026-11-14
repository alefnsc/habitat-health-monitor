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

## Hardware

Circuit diagrams and the bill of materials are in `docs/` (DRAFT [confirm: hardware member to review before submission]).

Layout: two microcontrollers and a hub (decision D40, [confirm: hardware member to review before submission]).
- **Raspberry Pi 3 Model B** is the hub host (Mosquitto, hub, console), with nothing wired to its header. A laptop runs the hub instead if the Pi is not ready. Setup: `docs/pi-setup.md` (not yet run on hardware).
- **Arduino UNO R3** (the bench board; the ATmega328P side of an UNO+WiFi works the same) is the I/O board. It carries a DHT11 (`cabin-1`: cabin temperature and humidity, hobby estimates) and the alarm buzzer, and talks to the hub over USB serial. On an UNO+WiFi the ESP8266 side is unused. Wokwi twin: `firmware/wokwi/uno-rig/`.
- **NodeMCU (ESP8266)** is the `tilt-1` node: a sealed KY-017 tilt pod on the exercise weight, running on four Ni-MH AA cells (into VIN) and talking over Wi-Fi/MQTT. Wokwi twin, with an ESP32 standing in: `firmware/wokwi/tilt-esp32/`.
- Wearable vitals will come from a ring import (next step). No sensor that touches a person is cabled to anything.

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

Claude Code (Anthropic) helped plan, research, write code and tests, and draft documents. The team defined the idea and all design decisions, approved every threshold and wording choice, ran all hardware and validation work, and reviewed the outputs. Every AI-assisted commit carries a `Co-Authored-By` trailer. No AI-generated images, video or voice are used. Full disclosure: [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md).

## Licence

Apache-2.0. See `LICENSE`.
