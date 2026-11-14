#!/bin/sh
# Fails if sketch.ino is not byte-for-byte the real tilt-1 sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if cmp -s "$here/../../tilt-esp8266/tilt-esp8266.ino" "$here/sketch.ino"; then
  echo "sketch.ino matches tilt-esp8266.ino"
else
  echo "sketch.ino differs from firmware/tilt-esp8266/tilt-esp8266.ino: run firmware/wokwi/tilt-esp32/sync.sh" >&2
  exit 1
fi
