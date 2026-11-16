// bmp280_lite.h: a small register-level BMP280 driver over I2C, shared by the three node sketches.
//
// Canonical copy: firmware/bmp280/bmp280_lite.h. Each sketch folder carries a byte-identical copy
// (Arduino builds only see files next to the sketch). firmware/bmp280/sync.sh refreshes the copies,
// firmware/bmp280/check_sync.sh fails when one differs. This repository's own code, Apache-2.0.
//
// Educational prototype, not a medical device. The reading is cabin_p in hPa, a hobby estimate
// (datasheet absolute accuracy about +-1 hPa). The BMP280 temperature is used only inside the
// compensation (t_fine) and is never published: cabin_temp stays with the DHT11.
//
// Compensation: Bosch BMP280 datasheet (BST-BMP280-DS001), section 3.11.3, the 32-bit integer
// temperature formula and the 64-bit integer pressure formula. Left shifts of values that can be
// negative are written as multiplications (same result, no undefined behaviour).
//
// Everything above "#ifdef ARDUINO" is plain C++ with no Arduino calls, compiled on the host by
// firmware/bmp280/test/run_host_tests.sh.
#pragma once

#include <stdint.h>

namespace bmp280 {

// Calibration words from registers 0x88..0x9F (datasheet table 17), little-endian.
struct Calib {
  uint16_t T1;
  int16_t T2, T3;
  uint16_t P1;
  int16_t P2, P3, P4, P5, P6, P7, P8, P9;
};

static const uint8_t kCalibLen = 24;
static const int32_t kSkipped = 0x80000;  // a result register before the first conversion

// Chip id (register 0xD0): 0x58 for the BMP280 (0x56/0x57 on early samples), 0x60 for a BME280,
// which some "BMP280" boards carry. Both use the same pressure registers and formulas.
static inline bool knownChip(uint8_t id) { return id == 0x56 || id == 0x57 || id == 0x58 || id == 0x60; }

static inline uint16_t u16le(const uint8_t* b) { return (uint16_t)(b[0] | ((uint16_t)b[1] << 8)); }
static inline int16_t s16le(const uint8_t* b) { return (int16_t)u16le(b); }

// Fills c from the 24 calibration bytes. False when T1 or P1 is 0 or 0xFFFF (no chip, or a bus
// that reads all zeros or all ones), which would also make the pressure formula divide by zero.
static inline bool parseCalib(const uint8_t* b, Calib* c) {
  c->T1 = u16le(b + 0);
  c->T2 = s16le(b + 2);
  c->T3 = s16le(b + 4);
  c->P1 = u16le(b + 6);
  c->P2 = s16le(b + 8);
  c->P3 = s16le(b + 10);
  c->P4 = s16le(b + 12);
  c->P5 = s16le(b + 14);
  c->P6 = s16le(b + 16);
  c->P7 = s16le(b + 18);
  c->P8 = s16le(b + 20);
  c->P9 = s16le(b + 22);
  return c->T1 != 0 && c->T1 != 0xFFFF && c->P1 != 0 && c->P1 != 0xFFFF;
}

// 20-bit raw value from msb, lsb, xlsb (registers 0xF7..0xF9 or 0xFA..0xFC).
static inline int32_t raw20(const uint8_t* b) {
  return ((int32_t)b[0] << 12) | ((int32_t)b[1] << 4) | (int32_t)(b[2] >> 4);
}

// t_fine from the raw temperature (bmp280_compensate_T_int32).
static inline int32_t tFine(const Calib& c, int32_t adcT) {
  int32_t d1 = (adcT >> 3) - (int32_t)c.T1 * 2;
  int32_t var1 = (d1 * (int32_t)c.T2) >> 11;
  int32_t d2 = (adcT >> 4) - (int32_t)c.T1;
  int32_t var2 = (((d2 * d2) >> 12) * (int32_t)c.T3) >> 14;
  return var1 + var2;
}

// Temperature in 0.01 C (2508 = 25.08 C). Used by the tests only; the nodes never publish it.
static inline int32_t centiCelsius(int32_t tf) { return (tf * 5 + 128) >> 8; }

// Pressure in Pa as Q24.8 (value / 256 = Pa), from the raw pressure (bmp280_compensate_P_int64).
// 0 when the calibration would divide by zero.
static inline uint32_t pressureQ8(const Calib& c, int32_t tf, int32_t adcP) {
  int64_t var1 = (int64_t)tf - 128000;
  int64_t var2 = var1 * var1 * (int64_t)c.P6;
  var2 = var2 + var1 * (int64_t)c.P5 * 131072;         // << 17
  var2 = var2 + (int64_t)c.P4 * 34359738368LL;         // << 35
  var1 = ((var1 * var1 * (int64_t)c.P3) >> 8) + var1 * (int64_t)c.P2 * 4096;  // << 12
  var1 = ((140737488355328LL + var1) * (int64_t)c.P1) >> 33;                 // 1 << 47
  if (var1 == 0) return 0;
  int64_t p = 1048576 - (int64_t)adcP;
  p = ((p * 2147483648LL - var2) * 3125) / var1;  // << 31
  var1 = ((int64_t)c.P9 * (p >> 13) * (p >> 13)) >> 25;
  var2 = ((int64_t)c.P8 * p) >> 19;
  p = ((p + var1 + var2) >> 8) + (int64_t)c.P7 * 16;  // << 4
  return (uint32_t)p;
}

static inline float hPaFromQ8(uint32_t q8) { return (float)q8 / 25600.0f; }

// Operating range of the BMP280 (datasheet table 2): outside it the reading is out_of_range.
static inline bool inRange(float hpa) { return hpa >= 300.0f && hpa <= 1100.0f; }

enum Event : uint8_t { EV_NONE, EV_READING, EV_FOUND, EV_MISSING, EV_LOST };

// Presence bookkeeping, so a missing or failing module never stops the board and is reported once:
// probe at boot; while missing, probe again every kReprobeMs without printing again; after three
// failed reads in a row the module is lost (reported once) and probed again later.
struct Presence {
  static const uint32_t kReprobeMs = 30000;
  bool up;
  bool probed;
  bool saidMissing;
  uint8_t fails;
  uint32_t lastProbeMs;

  void reset() { up = probed = saidMissing = false; fails = 0; lastProbeMs = 0; }
  bool probeDue(uint32_t now) const {
    return !up && (!probed || (uint32_t)(now - lastProbeMs) >= kReprobeMs);
  }
  Event afterProbe(bool ok, uint32_t now) {
    probed = true;
    lastProbeMs = now;
    if (ok) {
      up = true;
      fails = 0;
      return EV_FOUND;
    }
    if (saidMissing) return EV_NONE;
    saidMissing = true;
    return EV_MISSING;
  }
  Event afterRead(bool ok, uint32_t now) {
    if (ok) {
      fails = 0;
      return EV_READING;
    }
    if (++fails < 3) return EV_NONE;
    up = false;
    fails = 0;
    saidMissing = true;  // "lost" is the one report; the re-probes that follow stay quiet
    lastProbeMs = now;
    return EV_LOST;
  }
};

}  // namespace bmp280

#ifdef ARDUINO
#include <Arduino.h>
#include <Wire.h>

namespace bmp280 {

// One module on the board's default Wire bus. The sketch calls Wire.begin() first.
// Normal mode: pressure x4 and temperature x1 oversampling, IIR filter x4, 500 ms standby, so a
// read is one 6-byte burst with no waiting (well under 1 ms at 100 kHz).
class Poller {
 public:
  Poller() : addr_(0), chip_(0), lastReadMs_(0) { presence_.reset(); }

  // Call often. Probes and reads only when due (every intervalMs), so the loop is never held up.
  // EV_READING sets *hpa; the other events are for a one-line "# bmp280 ..." diagnostic.
  Event poll(uint32_t now, uint32_t intervalMs, float* hpa) {
    if (presence_.probeDue(now)) {
      Event e = presence_.afterProbe(probe(), now);
      lastReadMs_ = now;
      return e;
    }
    if (!presence_.up || (uint32_t)(now - lastReadMs_) < intervalMs) return EV_NONE;
    lastReadMs_ = now;
    bool ok = read(hpa);
    return presence_.afterRead(ok, now);
  }

  uint8_t address() const { return addr_; }
  bool isBme280() const { return chip_ == 0x60; }

 private:
  bool regs(uint8_t reg, uint8_t* out, uint8_t n) {
    Wire.beginTransmission(addr_);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((uint8_t)addr_, (uint8_t)n) != n) return false;
    for (uint8_t i = 0; i < n; i++) out[i] = (uint8_t)Wire.read();
    return true;
  }

  bool put(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(addr_);
    Wire.write(reg);
    Wire.write(val);
    return Wire.endTransmission() == 0;
  }

  bool probe() {
    static const uint8_t kAddrs[2] = {0x76, 0x77};  // SDO to GND, SDO to 3V3
    for (uint8_t i = 0; i < 2; i++) {
      addr_ = kAddrs[i];
      uint8_t id = 0, b[kCalibLen];
      if (!regs(0xD0, &id, 1) || !knownChip(id)) continue;
      if (!regs(0x88, b, kCalibLen) || !parseCalib(b, &cal_)) continue;
      // config is only written reliably in sleep mode: sleep, then config, then normal mode.
      if (!put(0xF4, 0x00) || !put(0xF5, 0x88) || !put(0xF4, 0x2F)) continue;
      chip_ = id;
      return true;
    }
    addr_ = 0;
    return false;
  }

  bool read(float* hpa) {
    uint8_t b[6];
    if (!regs(0xF7, b, 6)) return false;
    int32_t adcP = raw20(b), adcT = raw20(b + 3);
    if (adcP == kSkipped || adcT == kSkipped) return false;  // reset or not configured (replugged)
    uint32_t q8 = pressureQ8(cal_, tFine(cal_, adcT), adcP);
    if (q8 == 0) return false;
    *hpa = hPaFromQ8(q8);
    return true;
  }

  Calib cal_;
  Presence presence_;
  uint8_t addr_, chip_;
  uint32_t lastReadMs_;
};

}  // namespace bmp280
#endif
