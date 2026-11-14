# Raspberry Pi 3 setup: hub and cabin node

Status: **not yet run on hardware.** `scripts/pi-setup.sh` passes `shellcheck` and `bash -n` and the cabin
node is host-tested with a fake I2C bus, but nothing here has been run on a Pi. Expect to fix small things.
Educational prototype, not a medical device.

Decision D36: a Raspberry Pi 3 Model B v1.2 is the hub host (Mosquitto, FastAPI hub, console) and also
runs the `cabin-1` node, reading the cabin sensors on its own I2C bus. The Uno side of the UNO+WiFi
board stays the exercise rig, connected to the Pi by USB serial. The vitals node stays on a battery
board (safety rule: nothing body-worn is cabled to the Pi, see `docs/safety-checklist.md`).

## What you need

- Pi 3 Model B v1.2 with Raspberry Pi OS **64-bit, Bookworm** (Lite is fine), SSH or a screen, network.
- A good 5 V 2.5 A supply. An SCD41 measurement peaks near 200 mA and a weak rail causes brown-outs.
- BME280 and SCD41 modules (3.3 V). Optional DHT22 with a 10 kOhm pull-up on the data line.

## Wiring (Pi 40-pin header)

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

## Run the script

```bash
git clone https://github.com/alefnsc/habitat-health-monitor.git
cd habitat-health-monitor
scripts/pi-setup.sh          # asks for sudo; about 10 minutes plus downloads
sudo reboot
```

What it does, in order:
1. `apt`: `mosquitto`, `mosquitto-clients`, `i2c-tools`, `curl`.
2. `raspi-config nonint do_i2c 0` and `do_onewire 0`; adds you to the `i2c`, `gpio` and `dialout` groups.
3. Installs `uv` with Astral's official installer, then `uv python install 3.12` (the OS ships 3.11), a
   `.venv`, and `uv pip install -e ".[dev,pi]"`. The `pi` extra adds `smbus2`.
4. Creates `.env` (mode 600, git-ignored) from `.env.example`.
5. Mosquitto: `mosquitto_passwd -c /etc/mosquitto/habitat.passwd habitat` runs interactively, then the
   script asks once more (hidden) for the same password to put in `.env`. A drop-in file
   `/etc/mosquitto/conf.d/habitat.conf` sets the listener on 1883 with `allow_anonymous false`. No secret is
   committed, and none is on a command line.
6. Renders `scripts/systemd/habitat-hub.service.in` and `habitat-cabin.service.in` into
   `/etc/systemd/system/`, enables them and starts the hub.

`scripts/pi-setup.sh --no-services` stops after step 4 (Python environment only).

## After the reboot

```bash
i2cdetect -y 1                                   # 0x76 or 0x77, and 0x62
systemctl status habitat-hub habitat-cabin
journalctl -u habitat-cabin -f                   # "# bme280 at 0x76", "# cabin-1 boot=1"
mosquitto_sub -h 127.0.0.1 -u habitat -P '<password>' -v -t 'habitat/v1/r/cabin-1'
```

Without a broker, bench-check the sensors alone: `.venv/bin/python -m nodes.cabin_pi --stdout`.

Things the script does not do:
- Build the console: copy `console/dist` (and `camera/dist`) to the Pi from the machine that built them [confirm].
- Set `HUB_SERIAL_PORT` (usually `/dev/ttyACM0` or `/dev/ttyUSB0` for the Uno rig) in `.env`. Edit it, then
  `sudo systemctl restart habitat-hub`.
- Open the Pi to the internet. The broker listens on the local network only because the router does not
  forward it; keep it that way.

## Cabin node, `nodes/cabin_pi`

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
