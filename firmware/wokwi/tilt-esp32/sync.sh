#!/bin/sh
# Refreshes sketch.ino, the copy you paste into wokwi.com, from the real tilt-1 sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cp "$here/../../tilt-esp8266/tilt-esp8266.ino" "$here/sketch.ino"
echo "sketch.ino refreshed from firmware/tilt-esp8266/tilt-esp8266.ino"
