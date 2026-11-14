#!/bin/sh
# Refreshes sketch.ino, the copy you paste into wokwi.com, from the real vitals sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cp "$here/../../vitals-esp32/vitals-esp32.ino" "$here/sketch.ino"
echo "sketch.ino refreshed from firmware/vitals-esp32/vitals-esp32.ino"
