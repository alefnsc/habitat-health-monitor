// Shared host runtime for the chip tests: captures what the chip registers and plays the bus master.
#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
#include "wokwi-api.h"
void chip_init(void);
}

struct Host {
  i2c_config_t cfg{};
  timer_config_t tcfg{};
  uint32_t timer_us = 0;
  struct Attr { std::string name; bool is_float; uint32_t u; float f; };
  std::vector<Attr> attrs;
  void set(const char* n, double v) {
    for (auto& a : attrs) if (a.name == n) { a.f = (float)v; a.u = (uint32_t)v; }
  }
};
extern Host H;

inline void tick() { H.tcfg.callback(H.tcfg.user_data); }
inline void bus_write(const std::vector<uint8_t>& bytes) {
  H.cfg.connect(H.cfg.user_data, H.cfg.address, false);
  for (auto b : bytes) H.cfg.write(H.cfg.user_data, b);
}
inline uint8_t bus_read_reg(uint8_t reg) {
  bus_write({reg});
  H.cfg.connect(H.cfg.user_data, H.cfg.address, true);
  return H.cfg.read(H.cfg.user_data);
}
