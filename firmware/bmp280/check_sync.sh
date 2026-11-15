#!/bin/sh
# Fails if a sketch's copy of bmp280_lite.h differs from firmware/bmp280/bmp280_lite.h.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bad=0
for s in exercise-uno tilt-esp8266 cabin-esp32; do
  cmp -s "$here/bmp280_lite.h" "$here/../$s/bmp280_lite.h" || {
    echo "firmware/$s/bmp280_lite.h differs from firmware/bmp280/bmp280_lite.h: run firmware/bmp280/sync.sh" >&2
    bad=1
  }
done
[ "$bad" -eq 0 ] && echo "bmp280_lite.h copies match"
exit "$bad"
