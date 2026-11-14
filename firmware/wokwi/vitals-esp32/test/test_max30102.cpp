// Native test of max30102.chip.c: plays the SparkFun library's bus traffic and runs Maxim's reference
// algorithm (the real spo2_algorithm.cpp) on what the simulated chip serves.
#include <cassert>
#include <cstdio>
#include <vector>

#include "stub_runtime.h"
#include "spo2_algorithm.h"

static void wr(uint8_t reg, uint8_t v) { bus_write({reg, v}); }

// Same register values SparkFun's setup(60, 4, 2, 100, 411, 4096) ends with.
static void library_setup() {
  assert(bus_read_reg(0xFF) == 0x15);          // begin(): part id
  wr(0x09, 0x40);                              // soft reset
  assert((bus_read_reg(0x09) & 0x40) == 0);    // reset bit self-clears
  wr(0x08, 0x40 | 0x10);                       // sample average 4, rollover on
  wr(0x09, 0x03);                              // red + IR
  wr(0x0A, 0x20 | 0x04 | 0x03);                // 4096 range, 100 sps, 411 us
  wr(0x04, 0); wr(0x05, 0); wr(0x06, 0);       // clear FIFO
}

// Library check(): pointer difference, then burst read of the FIFO data register.
static std::vector<std::pair<uint32_t, uint32_t>> drain() {
  std::vector<std::pair<uint32_t, uint32_t>> out;
  uint8_t r = bus_read_reg(0x06), w = bus_read_reg(0x04);
  int n = w - r;
  if (n < 0) n += 32;
  if (n == 0) return out;
  bus_write({0x07});
  H.cfg.connect(H.cfg.user_data, H.cfg.address, true);
  for (int i = 0; i < n; i++) {
    uint8_t b[6];
    for (auto& x : b) x = H.cfg.read(H.cfg.user_data);
    uint32_t red = ((b[0] << 16) | (b[1] << 8) | b[2]) & 0x3FFFF;
    uint32_t ir = ((b[3] << 16) | (b[4] << 8) | b[5]) & 0x3FFFF;
    out.push_back({red, ir});
  }
  return out;
}

static void run_seconds(int s, std::vector<uint32_t>& red, std::vector<uint32_t>& ir) {
  for (int i = 0; i < s * 25; i++) {
    tick();
    if (i % 5 == 4)
      for (auto& p : drain()) { red.push_back(p.first); ir.push_back(p.second); }
  }
}

static void estimate(const std::vector<uint32_t>& red, const std::vector<uint32_t>& ir, int* hr, int* spo2,
                     int* hrv, int* spo2v) {
  uint32_t i100[100], r100[100];
  size_t off = ir.size() - 100;
  for (int i = 0; i < 100; i++) { i100[i] = ir[off + i]; r100[i] = red[off + i]; }
  int32_t s = 0, h = 0; int8_t sv = 0, hv = 0;
  maxim_heart_rate_and_oxygen_saturation(i100, 100, r100, &s, &sv, &h, &hv);
  *hr = h; *spo2 = s; *hrv = hv; *spo2v = sv;
}

int main() {
  chip_init();
  assert(H.cfg.address == 0x57);
  library_setup();
  tick();
  assert(H.timer_us == 40000);  // 100 sps / 4 averaged = 25 samples/s, as the firmware expects

  std::vector<uint32_t> red, ir;
  run_seconds(20, red, ir);
  assert(ir.size() >= 480);
  uint64_t sum = 0;
  for (size_t i = ir.size() - 25; i < ir.size(); i++) sum += ir[i];
  assert(sum / 25 >= 50000);  // finger present by default

  int hr, spo2, hv, sv;
  estimate(red, ir, &hr, &spo2, &hv, &sv);
  std::printf("default: hr=%d valid=%d spo2=%d valid=%d\n", hr, hv, spo2, sv);
  assert(hv == 1 && hr >= 68 && hr <= 76);
  assert(sv == 1 && spo2 >= 95 && spo2 <= 99);

  H.set("heartRate", 120);
  H.set("spo2", 92);
  red.clear(); ir.clear();
  run_seconds(20, red, ir);
  estimate(red, ir, &hr, &spo2, &hv, &sv);
  std::printf("120 bpm / 92 %%: hr=%d valid=%d spo2=%d valid=%d\n", hr, hv, spo2, sv);
  assert(hv == 1 && hr >= 113 && hr <= 127);
  assert(sv == 1 && spo2 >= 89 && spo2 <= 95);

  H.set("finger", 0);
  red.clear(); ir.clear();
  run_seconds(6, red, ir);
  sum = 0;
  for (size_t i = ir.size() - 25; i < ir.size(); i++) sum += ir[i];
  assert(sum / 25 < 50000);  // no finger: below the firmware's no_contact threshold

  // FIFO overflow: 40 samples with nobody reading keeps 31 and counts the loss.
  for (int i = 0; i < 40; i++) tick();
  uint8_t r = bus_read_reg(0x06), w = bus_read_reg(0x04);
  assert(((w - r) & 31) == 31 && bus_read_reg(0x05) > 0);
  std::puts("ok");
  return 0;
}
