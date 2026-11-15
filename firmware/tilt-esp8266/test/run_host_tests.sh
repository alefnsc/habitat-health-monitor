#!/bin/sh
# Host tests for the pure block of tilt-esp8266.ino and for the boot log the node keeps its
# boot number in (libraries/HabitatNode/src/BootLog.h). No board needed; needs a C++ compiler.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="${TMPDIR:-/tmp}/tilt-host-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
sed -n '/^\/\/ BEGIN PURE$/,/^\/\/ END PURE$/p' "$here/../tilt-esp8266.ino" > "$out/pure_block.h"
[ -s "$out/pure_block.h" ] || { echo "no BEGIN PURE block found" >&2; exit 2; }
c++ -std=c++17 -Wall -Werror -I "$out" "$here/test_pure.cpp" -o "$out/test_pure"
"$out/test_pure"
lib="$here/../../libraries/HabitatNode"
c++ -std=c++17 -Wall -Werror -I "$lib/src" "$lib/test/test_boot.cpp" -o "$out/test_boot"
"$out/test_boot"
