// Host tests for the pure part of bmp280_lite.h (run by run_host_tests.sh). No board needed.
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

#include "bmp280_lite.h"

using namespace bmp280;

static void le16(uint8_t* b, int v) {
  b[0] = (uint8_t)(v & 0xFF);
  b[1] = (uint8_t)((v >> 8) & 0xFF);
}

int main() {
  // Datasheet worked example (BST-BMP280-DS001 section 3.12): these trimming values with
  // adc_T = 519888 and adc_P = 415148 give t_fine = 128422, T = 25.08 C and p = 100653.27 Pa.
  const int words[12] = {27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000};
  uint8_t b[kCalibLen];
  for (int i = 0; i < 12; i++) le16(b + 2 * i, words[i]);
  Calib c;
  assert(parseCalib(b, &c));
  assert(c.T1 == 27504 && c.T2 == 26435 && c.T3 == -1000 && c.P1 == 36477);
  assert(c.P2 == -10685 && c.P6 == -7 && c.P8 == -14600 && c.P9 == 6000);

  int32_t tf = tFine(c, 519888);
  assert(tf == 128422);
  assert(centiCelsius(tf) == 2508);
  uint32_t q8 = pressureQ8(c, tf, 415148);
  assert(q8 == 25767233);                            // the 64-bit integer formula, Q24.8
  assert(fabs(q8 / 256.0 - 100653.27) < 0.05);       // the datasheet's double-precision result
  assert(fabsf(hPaFromQ8(q8) - 1006.5327f) < 0.001f);

  // Raw 20-bit values: msb, lsb, top nibble of xlsb.
  const uint8_t raw[3] = {0x65, 0x5A, 0xC0};  // 0x655AC = 415148
  assert(raw20(raw) == 415148);
  const uint8_t empty[3] = {0x80, 0x00, 0x00};
  assert(raw20(empty) == kSkipped);

  // A bus that reads all zeros or all ones is not a calibration block.
  uint8_t z[kCalibLen], f[kCalibLen];
  memset(z, 0, sizeof z);
  memset(f, 0xFF, sizeof f);
  assert(!parseCalib(z, &c) && !parseCalib(f, &c));
  Calib zero;
  memset(&zero, 0, sizeof zero);
  assert(pressureQ8(zero, tf, 415148) == 0);  // P1 = 0 would divide by zero

  assert(knownChip(0x58) && knownChip(0x60) && knownChip(0x56) && !knownChip(0x00) && !knownChip(0xFF));
  assert(inRange(1013.25f) && inRange(300.0f) && !inRange(299.9f) && !inRange(1100.1f) && !inRange(NAN));

  {  // missing at boot: reported once, re-probed quietly every 30 s, then found
    Presence p;
    p.reset();
    assert(p.probeDue(0));
    assert(p.afterProbe(false, 0) == EV_MISSING);
    assert(!p.probeDue(29999) && p.probeDue(30000));
    assert(p.afterProbe(false, 30000) == EV_NONE);
    assert(p.afterProbe(true, 60000) == EV_FOUND && p.up && !p.probeDue(90000));
  }
  {  // found, then two failed reads are tolerated and the third one loses it, once
    Presence p;
    p.reset();
    assert(p.afterProbe(true, 0) == EV_FOUND);
    assert(p.afterRead(true, 5000) == EV_READING);
    assert(p.afterRead(false, 10000) == EV_NONE && p.afterRead(false, 15000) == EV_NONE);
    assert(p.afterRead(true, 20000) == EV_READING);  // a good read resets the count
    assert(p.afterRead(false, 25000) == EV_NONE && p.afterRead(false, 30000) == EV_NONE);
    assert(p.afterRead(false, 35000) == EV_LOST && !p.up);
    assert(!p.probeDue(64999) && p.probeDue(65000));
    assert(p.afterProbe(false, 65000) == EV_NONE);  // still gone: no second report
    assert(p.afterProbe(true, 95000) == EV_FOUND);
  }
  {  // millis() wrap
    Presence p;
    p.reset();
    p.afterProbe(false, 0xFFFFF000u);
    assert(!p.probeDue(0x00000010u) && p.probeDue(0xFFFFF000u + 30000u));
  }
  puts("ok");
  return 0;
}
