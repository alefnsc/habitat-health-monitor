#!/bin/sh
# Fails if a copy in this folder differs from its source.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bad=0
check() { cmp -s "$1" "$2" || { echo "$2 differs from $1: run firmware/wokwi/full-bench/sync.sh" >&2; bad=1; }; }
check "$here/../../exercise-uno/exercise-uno.ino" "$here/sketch.ino"
check "$here/../uno-rig/wokwi_twin.h" "$here/wokwi_twin.h"
check "$here/../tilt-esp32/nimh-pack.chip.json" "$here/nimh-pack.chip.json"
check "$here/../tilt-esp32/nimh-pack.chip.c" "$here/nimh-pack.chip.c"
[ "$bad" -eq 0 ] && echo "full-bench copies match their sources"
exit "$bad"
