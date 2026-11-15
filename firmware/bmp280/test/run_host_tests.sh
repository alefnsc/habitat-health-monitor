#!/bin/sh
# Host tests for the pure part of bmp280_lite.h, and the check that every sketch copy matches it.
# No board needed; needs a C++ compiler.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="${TMPDIR:-/tmp}/bmp280-host-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
c++ -std=c++17 -Wall -Wextra -Werror -I "$here/.." "$here/test_bmp280.cpp" -o "$out/test_bmp280"
"$out/test_bmp280"
"$here/../check_sync.sh"
