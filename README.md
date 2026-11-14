# Habitat Health Monitor

A crew-facing health monitor for a space habitat that keeps working with no link to Earth. Real sensor circuits (ESP32, ESP8266, Arduino Uno) feed a local hub. The hub checks every reading against a stated source: NASA-STD-3001 for the cabin and radiation, and labelled clinical references (not NASA-published) for vital signs. It then tells the astronaut what to do and whom to tell, and syncs to a public "ground segment" page over a simulated Mars link with light-time delay and blackouts. It is not a medical device: hobby-sensor values are labelled estimates, and it never diagnoses.

Built during the NASA Space Apps Challenge 2026 (challenge: *Create Health Monitoring Software for Astronauts on Space Missions*). Licensed under Apache-2.0.

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

## Links

See `docs/decisions/links.md`.

## AI use

AI coding assistants were used to write parts of this project. Full disclosure: `docs/AI_DISCLOSURE.md` (added during the event).
