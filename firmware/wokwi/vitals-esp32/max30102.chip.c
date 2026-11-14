// Simulated MAX30102 for the Wokwi twin of the vitals node. Not a model of a real finger or of the real
// chip's analog front end: it answers the registers the SparkFun MAX3010x library uses (I2C 0x57,
// PART_ID 0xFF = 0x15) and serves a synthetic PPG whose rate, SpO2 ratio and finger state come from
// three controls. Reading it proves the firmware path (FIFO, windows, flags), not any measurement.
#include "wokwi-api.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define REG_FIFO_WR 0x04
#define REG_FIFO_OVF 0x05
#define REG_FIFO_RD 0x06
#define REG_FIFO_DATA 0x07
#define REG_FIFO_CFG 0x08
#define REG_MODE 0x09
#define REG_SPO2_CFG 0x0A
#define REG_PART_ID 0xFF
#define REG_REV_ID 0xFE
#define FIFO_DEPTH 32

typedef struct {
  uint8_t regs[256];
  uint32_t fifo[FIFO_DEPTH][2];  // red, ir (18 bit)
  uint8_t wr, rd;
  uint8_t cur_reg;
  bool have_reg;     // first byte of a write transaction is the register address
  uint8_t byte_idx;  // position inside the sample being read from FIFO_DATA
  uint32_t sample_no;
  uint32_t attr_finger, attr_hr, attr_spo2;
  timer_t timer;
  uint32_t timer_us;
} chip_state_t;

static const uint16_t kRates[8] = {50, 100, 200, 400, 800, 1000, 1600, 3200};

// Synthetic PPG: DC with a dip on every beat (reflective sensors see less light at systole).
// SpO2 sets the ratio of ratios R through the empirical quadratic -45.060 R^2 + 30.354 R + 94.845.
static void gen_ppg(double t, double bpm, int finger, double spo2, uint32_t *red, uint32_t *ir) {
  if (!finger) {
    *red = 1800;
    *ir = 2200;  // below the 50,000 no-finger threshold
    return;
  }
  double phase = fmod(t * bpm / 60.0, 1.0);
  double w = 0.5 * (1.0 - cos(2.0 * M_PI * phase));
  w *= w;  // one peak per beat
  double a = -45.060, b = 30.354, c = 94.845 - spo2;
  double disc = b * b - 4.0 * a * c;
  double r = disc >= 0 ? (-b - sqrt(disc)) / (2.0 * a) : 0.4;  // larger root: SpO2 falls as R rises
  if (r < 0.2) r = 0.2;
  if (r > 1.8) r = 1.8;
  double ir_dc = 120000.0, ir_ac = 3600.0;  // 3 % pulsatile
  double red_dc = 100000.0, red_ac = r * (ir_ac / ir_dc) * red_dc;
  *ir = (uint32_t)(ir_dc - ir_ac * w + 0.5);
  *red = (uint32_t)(red_dc - red_ac * w + 0.5);
}

static uint8_t count(chip_state_t *s) { return (uint8_t)((s->wr - s->rd) & (FIFO_DEPTH - 1)); }

static void on_timer(void *user_data) {
  chip_state_t *s = (chip_state_t *)user_data;
  uint8_t mode = s->regs[REG_MODE] & 0x07;
  if (mode != 2 && mode != 3 && mode != 7) return;
  uint32_t red, ir;
  uint16_t avg = (uint16_t)(1u << ((s->regs[REG_FIFO_CFG] >> 5) & 7));
  uint16_t rate = kRates[(s->regs[REG_SPO2_CFG] >> 2) & 7];
  double t = (double)s->sample_no * avg / rate;
  s->sample_no++;
  gen_ppg(t, (double)attr_read(s->attr_hr), (int)attr_read(s->attr_finger), (double)attr_read(s->attr_spo2),
          &red, &ir);
  if (count(s) == FIFO_DEPTH - 1) {  // full: the oldest sample is lost
    s->rd = (uint8_t)((s->rd + 1) & (FIFO_DEPTH - 1));
    if (s->regs[REG_FIFO_OVF] < 0x1F) s->regs[REG_FIFO_OVF]++;
  }
  s->fifo[s->wr][0] = red;
  s->fifo[s->wr][1] = ir;
  s->wr = (uint8_t)((s->wr + 1) & (FIFO_DEPTH - 1));
}

static void update_timer(chip_state_t *s) {
  uint16_t avg = (uint16_t)(1u << ((s->regs[REG_FIFO_CFG] >> 5) & 7));
  uint16_t rate = kRates[(s->regs[REG_SPO2_CFG] >> 2) & 7];
  uint32_t us = (uint32_t)(1000000.0 * avg / rate);
  if (us != s->timer_us) {
    s->timer_us = us;
    timer_start(s->timer, us, true);
  }
}

static void soft_reset(chip_state_t *s) {
  memset(s->regs, 0, sizeof s->regs);
  s->regs[REG_PART_ID] = 0x15;
  s->regs[REG_REV_ID] = 0x03;
  s->wr = s->rd = 0;
  s->sample_no = 0;
}

static bool on_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *s = (chip_state_t *)user_data;
  (void)address;
  if (!read) s->have_reg = false;  // a write transaction starts with the register address
  return true;
}

static uint8_t on_read(void *user_data) {
  chip_state_t *s = (chip_state_t *)user_data;
  uint8_t r = s->cur_reg;
  if (r == REG_FIFO_WR) return s->wr;
  if (r == REG_FIFO_RD) return s->rd;
  if (r == REG_FIFO_DATA) {  // red then IR, three bytes each, MSB first; the pointer advances per sample
    uint32_t v = s->fifo[s->rd][s->byte_idx / 3];
    uint8_t shift = (uint8_t)(16 - 8 * (s->byte_idx % 3));
    uint8_t out = (uint8_t)(v >> shift);
    if (++s->byte_idx >= 6) {
      s->byte_idx = 0;
      if (count(s) > 0) s->rd = (uint8_t)((s->rd + 1) & (FIFO_DEPTH - 1));
    }
    return out;
  }
  s->cur_reg = (uint8_t)(r + 1);  // other registers auto-increment
  return s->regs[r];
}

static bool on_write(void *user_data, uint8_t data) {
  chip_state_t *s = (chip_state_t *)user_data;
  if (!s->have_reg) {
    s->cur_reg = data;
    s->have_reg = true;
    s->byte_idx = 0;
    return true;
  }
  uint8_t r = s->cur_reg;
  if (r == REG_PART_ID || r == REG_REV_ID) return true;  // read-only
  if (r == REG_MODE && (data & 0x40)) {                    // RESET bit: self-clearing
    soft_reset(s);
    return true;
  }
  if (r == REG_FIFO_WR) s->wr = data & (FIFO_DEPTH - 1);
  else if (r == REG_FIFO_RD) s->rd = data & (FIFO_DEPTH - 1);
  else if (r == REG_FIFO_OVF) s->regs[r] = data;
  else s->regs[r] = data;
  if (r == REG_FIFO_CFG || r == REG_SPO2_CFG || r == REG_MODE) update_timer(s);
  s->cur_reg = (uint8_t)(r + 1);
  return true;
}

void chip_init(void) {
  static chip_state_t state;
  chip_state_t *s = &state;
  memset(s, 0, sizeof *s);
  soft_reset(s);
  s->attr_finger = attr_init("finger", 1);
  s->attr_hr = attr_init("heartRate", 72);
  s->attr_spo2 = attr_init("spo2", 97);
  timer_config_t tc = {.callback = on_timer, .user_data = s};
  s->timer = timer_init(&tc);
  i2c_config_t cfg = {
      .address = 0x57,
      .scl = pin_init("SCL", INPUT_PULLUP),
      .sda = pin_init("SDA", INPUT_PULLUP),
      .connect = on_connect,
      .read = on_read,
      .write = on_write,
      .disconnect = NULL,
      .user_data = s,
  };
  i2c_init(&cfg);
  printf("MAX30102 (simulated) ready at 0x57\n");
}
