#!/usr/bin/env bash
# Habitat hub setup for a Raspberry Pi 3 Model B on Raspberry Pi OS 64-bit (Bookworm).
# D40: the Pi is the hub host only; cabin-1 comes from the UNO I/O board over USB serial.
# NOT YET RUN ON HARDWARE. Read docs/pi-setup.md first; run as your normal user (it uses sudo).
# Safe to run again: each step checks before changing anything.
#   scripts/pi-setup.sh [--no-services]    (--no-services stops after the Python environment)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
PASSWD_FILE=/etc/mosquitto/habitat.passwd
MQTT_USER=habitat
NO_SERVICES=0
[ "${1:-}" = "--no-services" ] && NO_SERVICES=1

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run as your normal user, not root (sudo is called where needed)"
[ "$(uname -m)" = "aarch64" ] || printf 'warning: expected a 64-bit Pi (aarch64), found %s\n' "$(uname -m)" >&2
# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
[ "${VERSION_CODENAME:-}" = "bookworm" ] || printf 'warning: written for Bookworm, found %s\n' "${VERSION_CODENAME:-unknown}" >&2

say "1/6 apt packages: mosquitto, mosquitto-clients, i2c-tools, curl"
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients i2c-tools curl ca-certificates

say "2/6 enable I2C and 1-Wire (a reboot is needed before they appear)"
if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_i2c 0
  sudo raspi-config nonint do_onewire 0
else
  printf 'raspi-config not found: enable I2C and 1-Wire by hand (see docs/pi-setup.md)\n' >&2
fi
for g in i2c gpio dialout; do
  getent group "$g" >/dev/null && sudo usermod -aG "$g" "$RUN_USER"
done

say "3/6 uv, Python 3.12 and the virtualenv (Bookworm ships 3.11)"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  # Official installer from Astral (https://docs.astral.sh/uv/). Read it first if you prefer.
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
cd "$REPO"
uv python install 3.12
[ -d .venv ] || uv venv --python 3.12 .venv
# shellcheck disable=SC1091
. .venv/bin/activate
uv pip install -e ".[dev,pi]"

say "4/6 .env from .env.example (never committed)"
if [ ! -f .env ]; then
  ( umask 077 && cp .env.example .env )
  printf 'created %s/.env (mode 600)\n' "$REPO"
fi

if [ "$NO_SERVICES" -eq 1 ]; then
  say "stopping here (--no-services)"
  exit 0
fi

say "5/6 Mosquitto: password file and listener"
if [ ! -f "$PASSWD_FILE" ]; then
  printf 'Choose the broker password for user "%s". mosquitto_passwd will ask twice.\n' "$MQTT_USER"
  sudo mosquitto_passwd -c "$PASSWD_FILE" "$MQTT_USER"
fi
sudo chown root:mosquitto "$PASSWD_FILE"
sudo chmod 640 "$PASSWD_FILE"
sudo tee /etc/mosquitto/conf.d/habitat.conf >/dev/null <<CONF
# Written by scripts/pi-setup.sh. Persistence comes from the package's main config.
listener 1883
allow_anonymous false
password_file $PASSWD_FILE
CONF
if ! grep -q '^HUB_MQTT_PASS=.\+' .env; then
  printf 'Type the same password once more for .env (hidden): '
  read -rs pw
  printf '\n'
  [ -n "$pw" ] || die "empty password"
  # Rewrite the line without putting the password on a command line.
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  while IFS= read -r line; do
    case "$line" in
      HUB_MQTT_PASS=*) printf 'HUB_MQTT_PASS=%s\n' "$pw" ;;
      HUB_MQTT_USER=*) printf 'HUB_MQTT_USER=%s\n' "$MQTT_USER" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < .env > "$tmp"
  mv "$tmp" .env
  unset pw
fi
grep -q '^CABIN_I2C_BUS=' .env || printf 'CABIN_I2C_BUS=1\nCABIN_DHT_GPIO=\nCABIN_STATE_DIR=var\n' >> .env
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

say "6/6 systemd units for the hub (habitat-cabin is installed, not enabled: D40)"
for unit in habitat-hub habitat-cabin; do
  sed -e "s|@USER@|$RUN_USER|g" -e "s|@REPO@|$REPO|g" "scripts/systemd/$unit.service.in" \
    | sudo tee "/etc/systemd/system/$unit.service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable habitat-hub
sudo systemctl disable --now habitat-cabin 2>/dev/null || true  # a pre-D40 install had it enabled
sudo systemctl restart habitat-hub
printf 'habitat-cabin is installed but not enabled: in D40 cabin-1 comes from the UNO (set HUB_SERIAL_PORT in .env).\n'

cat <<DONE

Done. Next:
  1. sudo reboot            (I2C, 1-Wire and the new groups take effect)
  2. ls /dev/ttyACM* /dev/ttyUSB*   (the UNO I/O board), then set HUB_SERIAL_PORT in .env
  3. sudo systemctl restart habitat-hub && systemctl status habitat-hub
  4. curl -s http://127.0.0.1:8000/api/status   (cabin-1 readings every 5 s once the UNO is on USB)
Not yet run on hardware: report anything that differs.
DONE
