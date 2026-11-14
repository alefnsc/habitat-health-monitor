#!/bin/sh
# Fails if sketch.ino is not byte-for-byte the real exercise-uno sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if cmp -s "$here/../../exercise-uno/exercise-uno.ino" "$here/sketch.ino"; then
  echo "sketch.ino matches exercise-uno.ino"
else
  echo "sketch.ino differs from firmware/exercise-uno/exercise-uno.ino: run firmware/wokwi/uno-rig/sync.sh" >&2
  exit 1
fi
