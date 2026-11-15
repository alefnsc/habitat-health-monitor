# Raspberry Pi 3 setup: the hub host

Status: **not yet run on hardware.** `scripts/pi-setup.sh` passes `shellcheck` and `bash -n` and the cabin
node is host-tested with a fake I2C bus, but nothing here has been run on a Pi. Expect to fix small things.
The bring-up order below was written on 2026-11-15, before the first run on a Pi.
Educational prototype, not a medical device.

Decision D40 (amends D36): a Raspberry Pi 3 Model B v1.2 is the hub host (Mosquitto, FastAPI hub, console) and
nothing else. **Nothing is wired to its 40-pin header.** The UNO I/O board (an Arduino UNO R3 on the bench, or the ATmega328P
side of an UNO+WiFi board, with a DHT11 and the buzzer) plugs into a Pi USB port. It sends `cabin-1` readings over serial and takes the alarm
commands. The `tilt-1` NodeMCU runs on its own cells and reaches the broker over Wi-Fi. A laptop can run the same hub
when the Pi is not ready: `scripts/dev-up.sh`.

## Connections

The Pi takes these, and nothing else:

| Port on the Pi | What goes in | Notes |
|---|---|---|
| micro-USB (the only one) | 5 V 2.5 A supply | plug it in last: the Pi has no power switch |
| microSD slot, under the board, on the edge opposite the USB ports | the card from step 1, 8 GB or more | label facing down |
| any of the four USB-A ports | the UNO I/O board's USB cable | the Pi powers the UNO, which shows up as `/dev/ttyACM0` |
| Wi-Fi | the bench network, 2.4 GHz | the Pi 3 Model B has no 5 GHz radio |
| HDMI | a screen, optional | only if SSH cannot find `habitat.local` |

- **Nothing is wired to the 40-pin header.** The KY-017 goes to the NodeMCU (S to D5, + to 3V3, − to GND), and the
  NodeMCU's 4 × Ni-MH pack goes to the NodeMCU's VIN and GND. Neither ever touches the Pi. If a wire runs to the
  Pi's pins, take it off before the supply goes in.
- The LAN jack is not used.
- Two settings change when the Pi becomes the hub:
  - in the hub's `.env` on the Pi: `HUB_SERIAL_PORT=/dev/ttyACM0` (step 10);
  - in the NodeMCU's `secrets.h`: `MQTT_HOST` becomes the Pi's address from `hostname -I` (step 14). The ESP8266
    does not resolve `.local` names, so it needs the address. Flash it last, once the Pi hub works: until then the
    laptop hub stays a working fallback.

## What you need

- Pi 3 Model B v1.2, a 5 V 2.5 A micro-USB supply and a microSD card of 8 GB or more.
- Raspberry Pi OS Lite (64-bit), written with Raspberry Pi Imager. Imager's current release is based on Debian 13
  (Trixie), with Python 3.13; the older Bookworm image (Python 3.11) works the same way. Either way the script
  installs CPython 3.12 with `uv`, because the repo needs 3.12 (`pyproject.toml`).
- The UNO I/O board on a USB cable (it is powered from the Pi).
- A laptop on the same network, with Node.js, to build the console and camera pages. The Pi 3 has 1 GB of RAM and
  does not build them.

## Bring-up, in order

Every password is typed by the person at the bench: in Imager, at `sudo`, at `mosquitto_passwd` and at the script's
hidden prompt. None goes on a command line or into a commit. About an hour without surprises.

On the laptop:

1. **Write the card.** Raspberry Pi Imager (macOS: `brew install --cask raspberry-pi-imager`): device Raspberry Pi 3,
   OS Raspberry Pi OS Lite (64-bit), the microSD as storage. In the customisation: hostname `habitat`, user
   `habitat` with a password, the bench Wi-Fi name and password, country BR, time zone `America/Sao_Paulo`, SSH on
   (password or the laptop's public key).
2. **Plug in and boot.** Card in, HDMI if wanted, the supply last. The first boot takes 2 to 5 minutes and reboots
   once. The UNO stays on the laptop until step 9.
3. **Log in** and note the Pi's address for step 14:

   ```bash
   ssh habitat@habitat.local
   hostname -I
   ```

   If `habitat.local` does not resolve, read the address from the router or from a screen.

On the Pi:

4. **Clone.**

   ```bash
   sudo apt update && sudo apt install -y git
   git clone https://github.com/alefnsc/habitat-health-monitor.git && cd habitat-health-monitor
   ```

5. **Run the script** (15 to 25 minutes, mostly downloads; what it does is listed below):

   ```bash
   scripts/pi-setup.sh
   ```

   On Trixie it warns that it was written for Bookworm, then carries on. Give the broker the same password as the
   laptop's broker, so the NodeMCU's `MQTT_PASS` keeps working.
6. **The NodeMCU's broker user.** On the laptop, `grep '^#define MQTT_USER' firmware/tilt-esp8266/secrets.h` prints
   that one line. If the user is not `habitat`, add it on the Pi with the NodeMCU's password. Never pass `-c` here:
   it would recreate the file and drop `habitat`.

   ```bash
   sudo mosquitto_passwd /etc/mosquitto/habitat.passwd <user>
   sudo chown root:mosquitto /etc/mosquitto/habitat.passwd && sudo chmod 640 /etc/mosquitto/habitat.passwd
   sudo systemctl restart mosquitto
   ```

7. `sudo reboot`, then log in again.

On the laptop:

8. **Build and copy the pages.** The hub serves `console/dist` and `camera/dist`, and answers 503 until they exist.
   Build them from the commit the Pi cloned, then copy them:

   ```bash
   npm --prefix console ci && npm --prefix console run build
   npm --prefix camera ci && npm --prefix camera run build
   scp -r console/dist habitat@habitat.local:habitat-health-monitor/console/
   scp -r camera/dist habitat@habitat.local:habitat-health-monitor/camera/
   ```

   `ground/` is the public page (`docs/deploy-public.md`); the hub does not serve it.

On the bench:

9. **Move the UNO's USB cable** from the laptop to any USB port on the Pi.

On the Pi:

10. **Point the hub at the UNO.**

    ```bash
    cd ~/habitat-health-monitor && ls /dev/ttyACM* /dev/ttyUSB*
    sed -i 's|^HUB_SERIAL_PORT=.*|HUB_SERIAL_PORT=/dev/ttyACM0|' .env
    sudo systemctl restart habitat-hub && journalctl -u habitat-hub -n 30 --no-pager
    ```

    The log shows `rig connected on /dev/ttyACM0`. A clone UNO with a CH340 chip shows up as `/dev/ttyUSB0`
    instead; use that name.
11. **Smoke test.** On the Pi, `vcgencmd get_throttled` prints `throttled=0x0`; any other value means the supply or
    its cable is too weak. From the laptop, `cabin-1` is online (for a serial node, `last_seen` moves only when the
    port connects or drops), and the newest DHT11 rows are 5 s apart, the last one a few seconds old (UTC):

    ```bash
    curl -s http://habitat.local:8000/api/status | python3 -c 'import json,sys; [print(n["node"], n["online"], n["last_seen"]) for n in json.load(sys.stdin)["nodes"]]'
    curl -s 'http://habitat.local:8000/api/readings?ind=cabin_temp&limit=3' | python3 -c 'import json,sys; [print(r["node"], r["seq"], r["measured_at"], r["val"], r["q"]) for r in json.load(sys.stdin)]'
    ```

On the laptop:

12. **Console:** `http://habitat.local:8000/`. A phone that does not resolve `.local` uses
    `http://<pi-address>:8000/`.
13. **Camera page.** Browsers give the webcam only to https or localhost pages, so reach the Pi through a tunnel and
    keep it open. Port 8001 avoids a hub that may still be running on the laptop's 8000.

    ```bash
    ssh -N -L 8001:127.0.0.1:8000 habitat@habitat.local
    ```

    Then open `http://localhost:8001/camera/` on the laptop.
14. **The tilt node, last**, and only once step 11 passes. Put the Pi's address in `secrets.h` (`sed -i ''` is the
    macOS form), unplug the cell pack, plug the NodeMCU's USB into the laptop, find its port with
    `arduino-cli board list`, flash, unplug USB and put the pack back:

    ```bash
    sed -i '' 's|^#define MQTT_HOST .*|#define MQTT_HOST "<pi-address>"|' firmware/tilt-esp8266/secrets.h
    arduino-cli compile --upload -p <port> --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266
    curl -s 'http://habitat.local:8000/api/readings?ind=tilt&limit=5'
    ```

    Tilt the weight: the value goes to 1, and back to 0 when the weight comes back.

**Back to the laptop hub.** Before step 14, put the UNO's cable back into the same laptop port: the laptop hub
reconnects by itself. After step 14, also flash the NodeMCU again with the laptop's address.

## What the script does

In order:
1. `apt`: `mosquitto`, `mosquitto-clients`, `i2c-tools`, `curl`.
2. `raspi-config nonint do_i2c 0` and `do_onewire 0`; adds you to the `i2c`, `gpio` and `dialout` groups.
3. Installs `uv` with Astral's official installer, then `uv python install 3.12` (Bookworm ships 3.11, Trixie
   3.13), a `.venv`, and `uv pip install -e ".[dev,pi]"`. The `pi` extra adds `smbus2`.
4. Creates `.env` (mode 600, git-ignored) from `.env.example`.
5. Mosquitto: `mosquitto_passwd -c /etc/mosquitto/habitat.passwd habitat` runs interactively, then the
   script asks once more (hidden) for the same password to put in `.env`. A drop-in file
   `/etc/mosquitto/conf.d/habitat.conf` sets the listener on 1883 with `allow_anonymous false`. No secret is
   committed, and none is on a command line.
6. Renders `scripts/systemd/habitat-hub.service.in` and `habitat-cabin.service.in` into
   `/etc/systemd/system/`, then enables and starts the hub. `habitat-cabin` is installed but **not enabled** (D40).

`mosquitto` and `habitat-hub` start at every boot. The hub keeps its SQLite database in `var/` inside the clone
(`HUB_DB=var/hub.db`) and creates `var/` itself.

`scripts/pi-setup.sh --no-services` stops after step 4 (Python environment only).

It does not:
- build or copy the console and camera pages (step 8);
- set `HUB_SERIAL_PORT` (step 10);
- start the link simulator or the ground receiver; the hub runs without them;
- open the Pi to the internet. The broker (1883) and the hub (8000) are reachable on the local network only,
  because the router does not forward them; keep it that way.

UNO+WiFi only: set its DIP switch to "USB to ATmega328" (`firmware/README.md`) before plugging it in. A plain UNO R3
has no switch.

## Optional, not used in D40: cabin sensors on the Pi header

Only if a BME280 or SCD41 is fitted later. `nodes/cabin_pi` also publishes as `cabin-1`, so run it **instead of** the
UNO's DHT11, never next to it: build `exercise-uno` with `-DENABLE_DHT=0`, then
`sudo systemctl enable --now habitat-cabin`. Two sources on one node would collide on `(node, boot, seq)`, and the
hub would drop one copy as a duplicate.

| Pi pin | Signal | Goes to |
|---|---|---|
| 1 | 3V3 | BME280 VCC, SCD41 VCC (and the DHT22 VCC) |
| 3 | GPIO2 SDA | BME280 SDA, SCD41 SDA |
| 5 | GPIO3 SCL | BME280 SCL, SCD41 SCL |
| 6 (or 9, 14) | GND | all grounds |
| 7 | GPIO4 | DHT22 data, with 10 kOhm to 3V3 (only if fitted) |

BME280 address 0x76 (SDO to GND) or 0x77 (SDO to 3V3); the node tries both. SCD41 is at 0x62. Put
100 nF and 10 uF across the SCD41 supply. The pins are 3.3 V only: never connect 5 V to them.
Check the pin numbers against your module's silkscreen and the Pi pinout before powering on [confirm].

## Cabin node on the Pi, `nodes/cabin_pi` (optional, not enabled in D40)

Node `cabin-1`, contract v1, `src` `hobby`. Readings go to `habitat/v1/r/cabin-1` every 5 s at QoS 1;
`habitat/v1/status/cabin-1` carries a retained `online`, with a last will of `offline`.

| Indicator | Device | Notes |
|---|---|---|
| `cabin_temp`, `cabin_rh`, `cabin_p` | BME280 | forced mode, x1 oversampling; chip id must be 0x60 |
| `cabin_co2` | SCD41 | periodic mode; ambient pressure from the BME280 at boot and every 60 s; the sensor's own T and RH are discarded |
| `cabin_temp`, `cabin_rh` | DHT22 | optional, when `CABIN_DHT_GPIO` is set and `adafruit_dht` is installed |

Quality flags (team values, not datasheet values, except the ranges):
- `settling`: SCD41 for 60 s after measurement starts; BME280 on its first reading.
- `out_of_range`: BME280 outside -40 to 85 C, 0 to 100 %, 300 to 1100 hPa; SCD41 above 5000 ppm.
- `no_contact`: a sensor that worked has failed three reads in a row; the value is 0 and must be ignored.

The boot counter is a file, `var/cabin-1.boot` (`CABIN_STATE_DIR`). Unsent readings wait in a 32-entry ring
while the broker is away and carry the true `age_ms` when sent; the oldest are dropped first.

## Libraries and licences

| Component | Licence | Used for |
|---|---|---|
| `smbus2` | MIT | I2C access (`pi` extra) |
| `paho-mqtt` | EPL-2.0 OR BSD-3-Clause | MQTT (already a hub dependency) |
| `adafruit-circuitpython-dht` | MIT | optional DHT22 reader; not installed by the script [confirm licence at install] |
| `uv` | Apache-2.0 OR MIT | Python installer |
| Mosquitto (apt) | EPL-2.0 OR EDL-1.0 | broker |
| BME280 and SCD41 drivers | Apache-2.0 (this repository) | written from the Bosch and Sensirion datasheets |

## Checks

- `pytest -q nodes` runs the cabin node tests with a fake I2C bus (no Pi needed).
- The BME280 compensation is compared with the double-precision formulas in the Bosch datasheet
  (section 8.1, revision 1.23); the SCD41 CRC uses the Sensirion example (0xBEEF gives 0x92).
- On the Pi the bench checks are those of plan task F8, now through `mosquitto_sub`: a CO2 line every
  5 s, `settling` for the first 60 s, a rise of 200 ppm or more after a gentle exhale from 30 cm.
