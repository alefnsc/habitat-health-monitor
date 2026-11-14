// Host stand-in for Wokwi's wokwi-api.h, written from docs.wokwi.com/chips-api (not the real header).
// It only exists so the chip C files can be compiled and exercised natively. The real header is
// provided by Wokwi when the chip is built there.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define timer_t wokwi_stub_timer_t  // avoid POSIX timer_t on the host
typedef uint32_t pin_t;
typedef uint32_t timer_t;
typedef uint32_t i2c_dev_t;
enum { INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2 };

typedef struct {
  uint32_t address;
  pin_t scl, sda;
  bool (*connect)(void *user_data, uint32_t address, bool read);
  uint8_t (*read)(void *user_data);
  bool (*write)(void *user_data, uint8_t data);
  void (*disconnect)(void *user_data);
  void *user_data;
} i2c_config_t;

typedef struct {
  void (*callback)(void *user_data);
  void *user_data;
} timer_config_t;

pin_t pin_init(const char *name, uint32_t mode);
i2c_dev_t i2c_init(i2c_config_t *config);
timer_t timer_init(const timer_config_t *config);
void timer_start(timer_t timer_id, uint32_t micros, bool repeat);
uint32_t attr_init(const char *name, uint32_t default_value);
uint32_t attr_init_float(const char *name, float default_value);
uint32_t attr_read(uint32_t attr);
float attr_read_float(uint32_t attr);

void chip_init(void);

#ifdef __cplusplus
}
#endif
