#!/bin/sh
# Refreshes sketch.ino, the copy you paste into wokwi.com, from the real sketch.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
cp "$here/../../exercise-uno/exercise-uno.ino" "$here/sketch.ino"
echo "sketch.ino refreshed from firmware/exercise-uno/exercise-uno.ino"
