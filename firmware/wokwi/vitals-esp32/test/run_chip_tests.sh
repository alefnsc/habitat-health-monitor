#!/bin/sh
# Native tests for the two simulated chips, against a host stand-in for wokwi-api.h and the firmware's own
# decoder and SparkFun's reference algorithm. This does NOT prove the chips build or run on wokwi.com.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
twin="$here/.."
out="${TMPDIR:-/tmp}/wokwi-chip-test.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
SF="${SPARKFUN_SRC:-$HOME/Documents/Arduino/libraries/SparkFun_MAX3010x_Pulse_and_Proximity_Sensor_Library/src}"
[ -d "$SF" ] || { echo "SparkFun MAX3010x library not found (set SPARKFUN_SRC)" >&2; exit 2; }
sed -n '/^\/\/ BEGIN PURE$/,/^\/\/ END PURE$/p' "$twin/../../vitals-esp32/vitals-esp32.ino" > "$out/pure_block.h"
for chip in max30102 mlx90614; do
  cc -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -I "$here/stub" -c "$twin/$chip.chip.c" -o "$out/$chip.o"  # M_PI on glibc
done
c++ -std=c++17 -Wall -Werror -I "$here/stub" -I "$here" -isystem "$SF" -include "$here/stub/Arduino.h" \
  "$here/test_max30102.cpp" "$here/host_runtime.cpp" "$SF/spo2_algorithm.cpp" "$out/max30102.o" -o "$out/t_max"
c++ -std=c++17 -Wall -Wno-unused-function -Werror -I "$here/stub" -I "$here" -I "$out" \
  "$here/test_mlx90614.cpp" "$here/host_runtime.cpp" "$out/mlx90614.o" -o "$out/t_mlx"
"$out/t_max"
"$out/t_mlx"
