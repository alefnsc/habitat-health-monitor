#!/bin/sh
# Host tests for the pure block of exercise-uno.ino. No board needed.
# Needs a C++ compiler and ArduinoJson (ARDUINOJSON_SRC to override the default path).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="${TMPDIR:-/tmp}/exercise-uno-host-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
AJ="${ARDUINOJSON_SRC:-$HOME/Documents/Arduino/libraries/ArduinoJson/src}"
[ -d "$AJ" ] || AJ="$HOME/Arduino/libraries/ArduinoJson/src"
sed -n '/^\/\/ BEGIN PURE$/,/^\/\/ END PURE$/p' "$here/../exercise-uno.ino" > "$out/pure_block.h"
[ -s "$out/pure_block.h" ] || { echo "no BEGIN PURE block found" >&2; exit 2; }
c++ -std=c++17 -Wall -Werror -I "$out" -I "$AJ" "$here/test_pure.cpp" -o "$out/test_pure"
"$out/test_pure"
