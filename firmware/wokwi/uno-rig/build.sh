#!/bin/sh
# Compiles the twin build (the real exercise-uno sketch plus wokwi_twin.h) for the Uno into ./build,
# which wokwi.toml points at. Run from anywhere. Needs arduino-cli with arduino:avr@1.8.8 and
# DHT sensor library@1.4.7 (see firmware/README.md).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
"$here/check_sync.sh"
src="$here/build/src/exercise-uno"
mkdir -p "$src"
cp "$here/sketch.ino" "$src/exercise-uno.ino"
cp "$here/wokwi_twin.h" "$src/wokwi_twin.h"
arduino-cli compile --fqbn arduino:avr:uno --output-dir "$here/build" "$src"
echo "built: $here/build/exercise-uno.ino.hex"
