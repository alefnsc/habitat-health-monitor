#!/bin/sh
# Native tests for the Raspberry Pi hub chip, against a host stand-in for wokwi-api.h.
# This does NOT prove the chip builds or runs on wokwi.com.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="${TMPDIR:-/tmp}/wokwi-hub-chip-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
cc -std=c11 -Wall -Wextra -Werror -I "$here/stub" "$here/test_hub_chip.c" -o "$out/t_hub"
"$out/t_hub"
