#include "stub_runtime.h"
Host H;
extern "C" {
pin_t pin_init(const char*, uint32_t) { return 1; }
i2c_dev_t i2c_init(i2c_config_t* c) { H.cfg = *c; return 1; }
timer_t timer_init(const timer_config_t* c) { H.tcfg = *c; return 1; }
void timer_start(timer_t, uint32_t us, bool) { H.timer_us = us; }
uint32_t attr_init(const char* n, uint32_t d) { H.attrs.push_back({n, false, d, (float)d}); return (uint32_t)H.attrs.size() - 1; }
uint32_t attr_init_float(const char* n, float d) { H.attrs.push_back({n, true, (uint32_t)d, d}); return (uint32_t)H.attrs.size() - 1; }
uint32_t attr_read(uint32_t a) { return H.attrs[a].u; }
float attr_read_float(uint32_t a) { return H.attrs[a].f; }
}
