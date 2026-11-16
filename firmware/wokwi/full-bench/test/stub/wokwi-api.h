// Host stand-in for Wokwi's wokwi-api.h, written from docs.wokwi.com/chips-api (pins, UART, I2C, timers, attributes);
// it is not the real header. It only exists so rpi3-hub.chip.c can be compiled and exercised natively. The real
// header is provided by Wokwi when the chip is built there.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define timer_t wokwi_stub_timer_t  // avoid POSIX timer_t on the host
typedef uint32_t pin_t;
typedef uint32_t timer_t;
typedef uint32_t uart_dev_t;
enum { INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2, INPUT_PULLDOWN = 3, ANALOG = 4, OUTPUT_LOW = 16, OUTPUT_HIGH = 17 };

typedef struct {
  void *user_data;
  pin_t rx;
  pin_t tx;
  uint32_t baud_rate;
  void (*rx_data)(void *user_data, uint8_t byte);
  void (*write_done)(void *user_data);
} uart_config_t;

typedef struct {
  void *user_data;
  void (*callback)(void *user_data);
} timer_config_t;

pin_t pin_init(const char *name, uint32_t mode);
uart_dev_t uart_init(const uart_config_t *config);
bool uart_write(uart_dev_t uart, uint8_t *buffer, uint32_t count);
timer_t timer_init(const timer_config_t *config);
void timer_start(timer_t timer_id, uint32_t micros, bool repeat);
uint32_t attr_init(const char *name, uint32_t default_value);
uint32_t attr_read(uint32_t attr_id);
uint32_t attr_init_float(const char *name, float default_value);
float attr_read_float(uint32_t attr_id);

typedef uint32_t i2c_dev_t;
typedef struct {
  void *user_data;
  uint32_t address;
  pin_t scl;
  pin_t sda;
  bool (*connect)(void *user_data, uint32_t address, bool read);
  uint8_t (*read)(void *user_data);
  bool (*write)(void *user_data, uint8_t data);
  void (*disconnect)(void *user_data);
} i2c_config_t;
i2c_dev_t i2c_init(const i2c_config_t *config);

void chip_init(void);
