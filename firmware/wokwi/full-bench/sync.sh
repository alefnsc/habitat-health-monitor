#!/bin/sh
# Refreshes the copies in this folder from their sources: the UNO sketch, the twin header and the pack chip.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cp "$here/../../exercise-uno/exercise-uno.ino" "$here/sketch.ino"
cp "$here/../uno-rig/wokwi_twin.h" "$here/wokwi_twin.h"
cp "$here/../tilt-esp32/nimh-pack.chip.json" "$here/nimh-pack.chip.json"
cp "$here/../tilt-esp32/nimh-pack.chip.c" "$here/nimh-pack.chip.c"
echo "full-bench copies refreshed"
