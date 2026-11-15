#!/bin/sh
# Copies the canonical bmp280_lite.h next to each sketch that reads a BMP280.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
for s in exercise-uno tilt-esp8266 cabin-esp32; do
  cp "$here/bmp280_lite.h" "$here/../$s/bmp280_lite.h"
  echo "firmware/$s/bmp280_lite.h refreshed"
done
