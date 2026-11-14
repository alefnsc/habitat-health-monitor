#!/bin/sh
# Host tests for the pure block of vitals-esp32.ino. No board needed.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="${TMPDIR:-/tmp}/vitals-host-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
AJ="${ARDUINOJSON_SRC:-$HOME/Documents/Arduino/libraries/ArduinoJson/src}"
[ -d "$AJ" ] || AJ="$HOME/Arduino/libraries/ArduinoJson/src"
sed -n '/^\/\/ BEGIN PURE$/,/^\/\/ END PURE$/p' "$here/../vitals-esp32.ino" > "$out/pure_block.h"
[ -s "$out/pure_block.h" ] || { echo "no BEGIN PURE block found" >&2; exit 2; }
c++ -std=c++17 -Wall -Werror -I "$out" -I "$AJ" "$here/test_pure.cpp" -o "$out/test_pure"
"$out/test_pure"
