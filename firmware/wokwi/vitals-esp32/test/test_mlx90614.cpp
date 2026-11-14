// Native test of mlx90614.chip.c against the firmware's own decoder (the pure block of vitals-esp32.ino).
#include <cassert>
#include <cmath>
#include <cstdio>

#include "stub_runtime.h"
#include "pure_block.h"

static bool read_word(uint8_t cmd, float* c) {
  bus_write({cmd});
  H.cfg.connect(H.cfg.user_data, H.cfg.address, true);
  uint8_t lsb = H.cfg.read(H.cfg.user_data), msb = H.cfg.read(H.cfg.user_data), pec = H.cfg.read(H.cfg.user_data);
  return mlxDecode(0x5A, cmd, lsb, msb, pec, true, c);
}

int main() {
  chip_init();
  assert(H.cfg.address == 0x5A);
  float c = 0;
  assert(read_word(0x07, &c) && fabsf(c - 34.5f) < 0.02f);   // default object temperature
  assert(read_word(0x06, &c) && fabsf(c - 24.0f) < 0.02f);   // ambient
  H.set("objectTemp", 36.6);
  assert(read_word(0x07, &c) && fabsf(c - 36.6f) < 0.02f);
  H.set("objectTemp", 22.0);
  assert(read_word(0x07, &c) && fabsf(c - 22.0f) < 0.02f);
  std::puts("ok");
  return 0;
}
