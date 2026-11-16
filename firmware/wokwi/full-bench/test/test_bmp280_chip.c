// Native tests for the BMP280 chip (bmp280.chip.c) against the host stand-in for wokwi-api.h.
// The I2C transactions below follow what firmware/bmp280/bmp280_lite.h does on the UNO.
// This does NOT prove the chip builds or runs on wokwi.com; that is checked by hand in the saved project.
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "../bmp280.chip.c"

static i2c_config_t g_i2c;
static float g_attr[2];

pin_t pin_init(const char *name, uint32_t mode) { (void)name; (void)mode; return 1; }
i2c_dev_t i2c_init(const i2c_config_t *c) { g_i2c = *c; return 1; }
uint32_t attr_init_float(const char *name, float d) {
  uint32_t id = strcmp(name, "pressure") == 0 ? 0 : 1;
  assert(strcmp(name, "pressure") == 0 || strcmp(name, "temperature") == 0);
  g_attr[id] = d;
  return id;
}
float attr_read_float(uint32_t id) { return g_attr[id]; }

// Write a register pointer, then read n bytes (one repeated-start transaction, as Wire does).
static void read_regs(uint8_t reg, uint8_t *out, int n) {
  assert(g_i2c.connect(g_i2c.user_data, 0x76, false));
  assert(g_i2c.write(g_i2c.user_data, reg));
  assert(g_i2c.connect(g_i2c.user_data, 0x76, true));
  for (int i = 0; i < n; i++) out[i] = g_i2c.read(g_i2c.user_data);
  g_i2c.disconnect(g_i2c.user_data);
}

static void write_reg(uint8_t reg, uint8_t v) {
  assert(g_i2c.connect(g_i2c.user_data, 0x76, false));
  assert(g_i2c.write(g_i2c.user_data, reg));
  assert(g_i2c.write(g_i2c.user_data, v));
  g_i2c.disconnect(g_i2c.user_data);
}

// Driver-side maths from the datasheet, using the calibration read back over I2C.
static float measure_hpa(float *celsius) {
  uint8_t cal[24], d[6];
  read_regs(0x88, cal, 24);
  uint16_t t1 = (uint16_t)(cal[0] | cal[1] << 8);
  int16_t t2 = (int16_t)(cal[2] | cal[3] << 8), t3 = (int16_t)(cal[4] | cal[5] << 8);
  assert(t1 == T1 && t2 == T2 && t3 == T3);
  read_regs(0xF7, d, 6);
  int32_t adc_p = (int32_t)((uint32_t)d[0] << 12 | (uint32_t)d[1] << 4 | d[2] >> 4);
  int32_t adc_t = (int32_t)((uint32_t)d[3] << 12 | (uint32_t)d[4] << 4 | d[5] >> 4);
  assert(adc_p != 0x80000 && adc_t != 0x80000);  // never the "not converted yet" value
  int32_t tf = bmp_t_fine(adc_t);
  *celsius = (float)((tf * 5 + 128) >> 8) / 100.0f;
  return (float)bmp_pressure_q8(tf, adc_p) / 25600.0f;
}

static void test_datasheet_vectors(void) {
  int32_t tf = bmp_t_fine(519888);
  assert(((tf * 5 + 128) >> 8) == 2508);                      // 25.08 C
  float hpa = (float)bmp_pressure_q8(tf, 415148) / 25600.0f;  // 100653.27 Pa
  assert(fabsf(hpa - 1006.5327f) < 0.01f);
}

static void test_chip_id_and_address(void) {
  uint8_t id = 0;
  read_regs(0xD0, &id, 1);
  assert(id == 0x58);
  assert(!g_i2c.connect(g_i2c.user_data, 0x77, false));  // only 0x76 answers
}

static void test_driver_setup_writes_are_kept(void) {
  write_reg(0xF4, 0x00);
  write_reg(0xF5, 0x88);
  write_reg(0xF4, 0x2F);
  uint8_t ctrl[2];
  read_regs(0xF4, ctrl, 2);
  assert(ctrl[0] == 0x2F && ctrl[1] == 0x88);
}

static void test_reports_the_controls(void) {
  float t = 0;
  float p = measure_hpa(&t);
  assert(fabsf(p - 925.0f) < 0.02f);  // default control: São Paulo bench altitude
  assert(fabsf(t - 24.0f) < 0.02f);
  g_attr[0] = 1013.25f;
  g_attr[1] = 30.5f;
  p = measure_hpa(&t);
  assert(fabsf(p - 1013.25f) < 0.02f);
  assert(fabsf(t - 30.5f) < 0.02f);
}

int main(void) {
  chip_init();
  test_datasheet_vectors();
  test_chip_id_and_address();
  test_driver_setup_writes_are_kept();
  test_reports_the_controls();
  puts("bmp280 chip: ok");
  return 0;
}
