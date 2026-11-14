#!/bin/sh
# Fails if sketch.ino is not byte-for-byte the real vitals sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if cmp -s "$here/../../vitals-esp32/vitals-esp32.ino" "$here/sketch.ino"; then
  echo "sketch.ino matches vitals-esp32.ino"
else
  echo "sketch.ino differs from firmware/vitals-esp32/vitals-esp32.ino: run firmware/wokwi/vitals-esp32/sync.sh" >&2
  exit 1
fi
