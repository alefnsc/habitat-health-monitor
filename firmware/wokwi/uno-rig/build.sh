#!/bin/sh
# Compiles the real exercise-uno sketch for the Uno into ./build, which wokwi.toml points at.
# Run from anywhere. Needs arduino-cli with arduino:avr@1.8.8 and the libraries in firmware/README.md.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
"$here/check_sync.sh"
arduino-cli compile --fqbn arduino:avr:uno --output-dir "$here/build" "$here/../../exercise-uno"
echo "built: $here/build/exercise-uno.ino.hex"
