// Simulated MLX90614 (GY-906) for the Wokwi twin of the vitals node. SMBus 0x5A. Answers the RAM read
// word command the firmware uses (0x07 object 1, 0x06 ambient) with the 0.02 K per count encoding and a
// correct SMBus PEC. Temperatures come from two controls: this is a stand-in, not a skin model.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint32_t attr_object, attr_ambient;
  uint8_t cmd;
  bool have_cmd;
  uint8_t byte_idx;
} chip_state_t;

static uint8_t crc8(const uint8_t *d, int n) {
  uint8_t crc = 0;
  for (int i = 0; i < n; i++) {
    crc ^= d[i];
    for (int b = 0; b < 8; b++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

static uint16_t word_for(chip_state_t *s, uint8_t cmd) {
  float c;
  if (cmd == 0x06) c = attr_read_float(s->attr_ambient);
  else if (cmd == 0x07 || cmd == 0x08) c = attr_read_float(s->attr_object);
  else if (cmd == 0x2E) return 0x005A;  // EEPROM SMBus address register
  else return 0;
  float raw = (c + 273.15f) / 0.02f;
  if (raw < 0) raw = 0;
  if (raw > 65535) raw = 65535;
  return (uint16_t)(raw + 0.5f);
}

static bool on_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *s = (chip_state_t *)user_data;
  (void)address;
  if (!read) s->have_cmd = false;
  else s->byte_idx = 0;
  return true;
}

static uint8_t on_read(void *user_data) {
  chip_state_t *s = (chip_state_t *)user_data;
  uint16_t w = word_for(s, s->cmd);
  uint8_t lsb = (uint8_t)(w & 0xFF), msb = (uint8_t)(w >> 8);
  uint8_t pkt[5] = {0xB4, s->cmd, 0xB5, lsb, msb};  // 0x5A write, command, 0x5A read, data
  uint8_t out = s->byte_idx == 0 ? lsb : s->byte_idx == 1 ? msb : crc8(pkt, 5);
  if (s->byte_idx < 2) s->byte_idx++;
  else s->byte_idx = 0;
  return out;
}

static bool on_write(void *user_data, uint8_t data) {
  chip_state_t *s = (chip_state_t *)user_data;
  if (!s->have_cmd) {
    s->cmd = data;
    s->have_cmd = true;
    s->byte_idx = 0;
  }
  return true;
}

void chip_init(void) {
  static chip_state_t state;
  chip_state_t *s = &state;
  memset(s, 0, sizeof *s);
  s->attr_object = attr_init_float("objectTemp", 34.5f);
  s->attr_ambient = attr_init_float("ambientTemp", 24.0f);
  i2c_config_t cfg = {
      .address = 0x5A,
      .scl = pin_init("SCL", INPUT_PULLUP),
      .sda = pin_init("SDA", INPUT_PULLUP),
      .connect = on_connect,
      .read = on_read,
      .write = on_write,
      .disconnect = NULL,
      .user_data = s,
  };
  i2c_init(&cfg);
  printf("MLX90614 (simulated) ready at 0x5A\n");
}
