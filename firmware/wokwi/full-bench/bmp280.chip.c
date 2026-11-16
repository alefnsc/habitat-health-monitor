// BMP280 barometer (Wokwi custom chip) for the full-bench twin.
// It answers the registers that firmware/bmp280/bmp280_lite.h reads, at I2C address 0x76:
//   0xD0 chip id 0x58, 0x88..0x9F calibration (the datasheet's example values), 0xF3 status,
//   0xF4/0xF5 control (written, kept), 0xE0 reset, 0xF7..0xFC pressure and temperature results.
// The "pressure" (hPa) and "temperature" (C) controls set what it reports. The raw results are found by
// inverting the datasheet compensation, so the sketch's own maths gives the control values back.
// Wire it like the real module: VCC to 3.3V (never 5V), GND, SDA to A4, SCL to A5.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define BMP280_ADDR 0x76
#define BMP280_CHIP_ID 0x58

// Datasheet (BST-BMP280-DS001) example calibration.
static const uint16_t T1 = 27504;
static const int16_t T2 = 26435, T3 = -1000;
static const uint16_t P1 = 36477;
static const int16_t P2 = -10685, P3 = 3024, P4 = 2855, P5 = 140, P6 = -7, P7 = 15500, P8 = -14600, P9 = 6000;

typedef struct {
  uint8_t regs[256];
  uint8_t ptr;
  bool expect_reg;  // the first byte of a write transaction is the register pointer
  uint32_t attr_p;
  uint32_t attr_t;
} bmp_chip_t;

static int32_t bmp_t_fine(int32_t adc_t) {
  int32_t var1 = ((((adc_t >> 3) - ((int32_t)T1 << 1))) * ((int32_t)T2)) >> 11;
  int32_t d = (adc_t >> 4) - (int32_t)T1;
  int32_t var2 = (((d * d) >> 12) * ((int32_t)T3)) >> 14;
  return var1 + var2;
}

// Pressure in Pa as Q24.8 (datasheet 64-bit formula); 0 means "not computable".
static uint32_t bmp_pressure_q8(int32_t t_fine, int32_t adc_p) {
  int64_t var1 = (int64_t)t_fine - 128000;
  int64_t var2 = var1 * var1 * (int64_t)P6;
  var2 = var2 + var1 * (int64_t)P5 * 131072;  // << 17
  var2 = var2 + (int64_t)P4 * 34359738368LL;  // << 35
  var1 = ((var1 * var1 * (int64_t)P3) >> 8) + var1 * (int64_t)P2 * 4096;  // << 12
  var1 = ((140737488355328LL + var1) * (int64_t)P1) >> 33;  // 1 << 47
  if (var1 == 0) return 0;
  int64_t p = 1048576 - adc_p;
  p = ((p * 2147483648LL - var2) * 3125) / var1;  // << 31
  var1 = (((int64_t)P9) * (p >> 13) * (p >> 13)) >> 25;
  var2 = (((int64_t)P8) * p) >> 19;
  p = ((p + var1 + var2) >> 8) + (int64_t)P7 * 16;  // << 4
  return (uint32_t)p;
}

// Smallest raw temperature whose compensated value reaches `centi_c` (t_fine rises with adc_t).
static int32_t bmp_adc_t_for(int32_t centi_c) {
  int32_t lo = 1, hi = 0xFFFFF - 1;
  while (lo < hi) {
    int32_t mid = lo + (hi - lo) / 2;
    int32_t c = (bmp_t_fine(mid) * 5 + 128) >> 8;
    if (c < centi_c) lo = mid + 1; else hi = mid;
  }
  return lo;
}

// Raw pressure whose compensated value is closest to `pa_q8` (pressure falls as adc_p rises).
static int32_t bmp_adc_p_for(int32_t t_fine, uint32_t pa_q8) {
  int32_t lo = 1, hi = 0xFFFFF - 1;
  while (lo < hi) {
    int32_t mid = lo + (hi - lo) / 2;
    if (bmp_pressure_q8(t_fine, mid) > pa_q8) lo = mid + 1; else hi = mid;
  }
  return lo;
}

static void put16(uint8_t *r, uint16_t v) { r[0] = (uint8_t)(v & 0xFF); r[1] = (uint8_t)(v >> 8); }

static void bmp_load_calibration(bmp_chip_t *c) {
  uint8_t *r = &c->regs[0x88];
  put16(r + 0, T1); put16(r + 2, (uint16_t)T2); put16(r + 4, (uint16_t)T3);
  put16(r + 6, P1); put16(r + 8, (uint16_t)P2); put16(r + 10, (uint16_t)P3);
  put16(r + 12, (uint16_t)P4); put16(r + 14, (uint16_t)P5); put16(r + 16, (uint16_t)P6);
  put16(r + 18, (uint16_t)P7); put16(r + 20, (uint16_t)P8); put16(r + 22, (uint16_t)P9);
}

// Refresh the result registers from the controls (called at the start of each transaction).
static void bmp_update_results(bmp_chip_t *c, float hpa, float celsius) {
  int32_t adc_t = bmp_adc_t_for((int32_t)(celsius * 100.0f + (celsius >= 0 ? 0.5f : -0.5f)));
  int32_t adc_p = bmp_adc_p_for(bmp_t_fine(adc_t), (uint32_t)(hpa * 25600.0f + 0.5f));
  c->regs[0xF7] = (uint8_t)(adc_p >> 12);
  c->regs[0xF8] = (uint8_t)((adc_p >> 4) & 0xFF);
  c->regs[0xF9] = (uint8_t)((adc_p & 0x0F) << 4);
  c->regs[0xFA] = (uint8_t)(adc_t >> 12);
  c->regs[0xFB] = (uint8_t)((adc_t >> 4) & 0xFF);
  c->regs[0xFC] = (uint8_t)((adc_t & 0x0F) << 4);
}

static bool on_connect(void *user_data, uint32_t address, bool read) {
  bmp_chip_t *c = (bmp_chip_t *)user_data;
  if (address != BMP280_ADDR) return false;
  if (!read) c->expect_reg = true;
  bmp_update_results(c, attr_read_float(c->attr_p), attr_read_float(c->attr_t));
  return true;
}

static uint8_t on_read(void *user_data) {
  bmp_chip_t *c = (bmp_chip_t *)user_data;
  return c->regs[c->ptr++];
}

static bool on_write(void *user_data, uint8_t data) {
  bmp_chip_t *c = (bmp_chip_t *)user_data;
  if (c->expect_reg) {
    c->ptr = data;
    c->expect_reg = false;
    return true;
  }
  if (c->ptr == 0xF4 || c->ptr == 0xF5) c->regs[c->ptr] = data;  // control and config are kept
  c->ptr++;  // a reset (0xE0 = 0xB6) changes nothing the driver can see here
  return true;
}

static void on_disconnect(void *user_data) { (void)user_data; }

void chip_init(void) {
  bmp_chip_t *c = (bmp_chip_t *)calloc(1, sizeof(bmp_chip_t));
  c->regs[0xD0] = BMP280_CHIP_ID;
  bmp_load_calibration(c);
  c->attr_p = attr_init_float("pressure", 925.0f);
  c->attr_t = attr_init_float("temperature", 24.0f);
  const i2c_config_t cfg = {
    .user_data = c,
    .address = BMP280_ADDR,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_connect,
    .read = on_read,
    .write = on_write,
    .disconnect = on_disconnect,
  };
  i2c_init(&cfg);
}
