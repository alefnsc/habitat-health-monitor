// exercise-uno: the UNO I/O board on the UNO+WiFi's ATmega328P side (decision D40; F14-F16, D35).
//
// Educational prototype, not a medical device. Readings from hobby sensors are estimates.
//
// Link: USB serial, 250000 baud 8N1, to the hub. One contract-v1 reading per line (plain Serial
// output, no JSON library on the Uno). Lines starting with "# " are diagnostics. Command lines (D7)
// come in on the same port, one JSON object per line; every command is answered with one ack line.
// Two nodes share the link: cabin-1 (DHT11, BMP280) and exercise-1 (acks, and the rig channels if built).
//
// Pins: DHT11 data D2 | buzzer D8 | HX711 DOUT D3, SCK D4 | servo signal D6 | NTC out A0 | pulse A1.
// BMP280 (cabin_p on cabin-1, every 5 s): SDA A4, SCL A5, VCC on 3V3 (never 5V: the chip's limit is
// 3.6 V), CSB to 3V3 (I2C mode), SDO to GND (address 0x76) or 3V3 (0x77); both addresses are probed.
// The UNO drives I2C at 5 V: setup() switches the AVR's internal pull-ups on A4/A5 off after
// Wire.begin(), so only the module's own pull-ups, to 3.3 V, set the high level (3.3 V is above
// the AVR's 3.0 V input-high threshold). A bidirectional 3.3 V/5 V level shifter is the proper fix.
// The BMP280's own temperature is not published: cabin_temp stays with the DHT11.
//
// Build flags (D40 defaults: only the DHT11 and the buzzer are wired). A module that is not wired is
// compiled out, so a floating pin never publishes numbers (a floating HX711 DOUT reads as "ready"):
//   ENABLE_DHT=1  ENABLE_HX711=0  ENABLE_SERVO=0  ENABLE_NTC=0  ENABLE_KY039=0
//   ENABLE_BMP280=1 when bmp280_lite.h sits next to this file (the repository sketch folder; the
//   Wokwi twins have no such file and no BMP280 part, so they build without it). A module that does
//   not answer is reported once ("# bmp280 missing") and every other channel goes on.
//   BUZZER_PASSIVE=1 (the bench buzzer is passive, driven with tone(); 0 for an active one)  DHT_TYPE=DHT11
//   arduino-cli compile --fqbn arduino:avr:uno --build-property "build.extra_flags=-DENABLE_HX711=1" ...
// The HX711 RATE pin must be tied to DVDD for 80 SPS when the load cell is fitted.
//
// The Wokwi twin adds a wokwi_twin.h next to this file (DHT22 stand-in, passive buzzer). The real
// sketch folder has no such file, so the defaults above apply on the bench.
//
// The block between BEGIN PURE and END PURE is plain C++ with no Arduino calls. It is extracted and
// compiled on the host by firmware/exercise-uno/test/run_host_tests.sh.

#if __has_include("wokwi_twin.h")
#include "wokwi_twin.h"
#endif

#ifndef ENABLE_DHT
#define ENABLE_DHT 1
#endif
#ifndef ENABLE_HX711
#define ENABLE_HX711 0
#endif
#ifndef ENABLE_SERVO
#define ENABLE_SERVO 0
#endif
#ifndef ENABLE_NTC
#define ENABLE_NTC 0
#endif
#ifndef ENABLE_KY039
#define ENABLE_KY039 0
#endif
#ifndef BUZZER_PASSIVE
#define BUZZER_PASSIVE 1
#endif
#ifndef ENABLE_BMP280
#if __has_include("bmp280_lite.h")
#define ENABLE_BMP280 1
#else
#define ENABLE_BMP280 0
#endif
#endif

#include <EEPROM.h>
#if ENABLE_HX711
#include <HX711.h>
#endif
#if ENABLE_SERVO
#include <Servo.h>
#endif
#if ENABLE_DHT
#include <DHT.h>
#ifndef DHT_TYPE
#define DHT_TYPE DHT11
#endif
#endif
#if ENABLE_BMP280
#include <Wire.h>
#include "bmp280_lite.h"
#endif

#ifndef CELL_CAPACITY_KG
#define CELL_CAPACITY_KG 50  // rated capacity of the load cell, kg
#endif

// BEGIN PURE
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef NTC_BETA
#define NTC_BETA 3950.0f  // beta coefficient of the 10 k NTC (datasheet value, not measured)
#endif
#ifndef NTC_SERIES_OVER_R25
#define NTC_SERIES_OVER_R25 1.0f  // series resistor divided by the NTC resistance at 25 C
#endif
#ifndef HR_MIN_AMP
#define HR_MIN_AMP 8.0f  // smallest pulse amplitude (ADC counts) that counts as finger contact
#endif

// Command line (D7): {"v":1,"cmd":"servo","angle_deg":90} and friends. Substring scanning only.
struct Cmd {
  char name[14];
  bool hasAngle, hasOn, hasMass, on;
  long angle;
  float mass;
};

enum Capture : uint8_t { CAP_NONE, CAP_CAL, CAP_TARE };

static const float kGravity = 9.81f;            // Earth g, contract section 4.2
static const float kPlaceholderK = 1000.0f;     // counts per N until a calibration exists
static const uint8_t QF_SETTLING = 1 << 2;      // same bit order as ReadingFormat.h
static const uint8_t QF_NO_CONTACT = 1 << 1;
static const uint8_t QF_OUT_OF_RANGE = 1 << 4;

// Number to text with up to two decimals and no trailing zeros. Returns bytes written, 0 if it did
// not fit. Integer maths, because the AVR printf has no float support.
static size_t fmtVal(char* out, size_t cap, float v) {
  if (!(v == v)) v = 0.0f;
  if (v > 1e7f) v = 1e7f;
  if (v < -1e7f) v = -1e7f;
  bool neg = v < 0;
  if (neg) v = -v;
  uint32_t s = (uint32_t)(v * 100.0f + 0.5f);
  uint32_t whole = s / 100, frac = s % 100;
  if (s == 0) neg = false;
  int n;
  if (frac == 0)
    n = snprintf(out, cap, "%s%lu", neg ? "-" : "", (unsigned long)whole);
  else if (frac % 10 == 0)
    n = snprintf(out, cap, "%s%lu.%u", neg ? "-" : "", (unsigned long)whole, (unsigned)(frac / 10));
  else
    n = snprintf(out, cap, "%s%lu.%02u", neg ? "-" : "", (unsigned long)whole, (unsigned)frac);
  return (n < 0 || (size_t)n >= cap) ? 0 : (size_t)n;
}

// Flag names in the order of ReadingFormat.h: motion, no_contact, settling, leads_off, out_of_range.
static size_t fmtFlags(char* out, size_t cap, uint8_t q) {
  static const char* const names[5] = {"motion", "no_contact", "settling", "leads_off",
                                       "out_of_range"};
  size_t pos = 0;
  int n;
  if (q == 0) {
    n = snprintf(out, cap, "\"ok\"");
    return (n < 0 || (size_t)n >= cap) ? 0 : (size_t)n;
  }
  for (uint8_t i = 0; i < 5; i++) {
    if (!(q & (1 << i))) continue;
    if (pos >= cap) return 0;
    n = snprintf(out + pos, cap - pos, "%s\"%s\"", pos ? "," : "", names[i]);
    if (n < 0 || (size_t)n >= cap - pos) return 0;
    pos += (size_t)n;
  }
  return pos;
}

// One reading line, no newline. Returns length, 0 if it does not fit in cap.
static size_t buildReading(char* out, size_t cap, const char* node, uint32_t boot, uint32_t seq,
                           const char* ind, float val, const char* unit, const char* dev, uint8_t q) {
  int n = snprintf(out, cap,
                   "{\"v\":1,\"node\":\"%s\",\"boot\":%lu,\"seq\":%lu,\"age_ms\":0,"
                   "\"ind\":\"%s\",\"val\":",
                   node, (unsigned long)boot, (unsigned long)seq, ind);
  if (n < 0 || (size_t)n >= cap) return 0;
  size_t pos = (size_t)n;
  size_t m = fmtVal(out + pos, cap - pos, val);
  if (m == 0) return 0;
  pos += m;
  n = snprintf(out + pos, cap - pos, ",\"unit\":\"%s\",\"src\":\"hobby\",\"dev\":\"%s\",\"q\":[", unit,
               dev);
  if (n < 0 || (size_t)n >= cap - pos) return 0;
  pos += (size_t)n;
  m = fmtFlags(out + pos, cap - pos, q);
  if (m == 0) return 0;
  pos += m;
  n = snprintf(out + pos, cap - pos, "]}");
  if (n < 0 || (size_t)n >= cap - pos) return 0;
  return pos + (size_t)n;
}

// Ack line (Proposed addition 4). err may be NULL. cmd is expected to be already sanitised.
static size_t buildAck(char* out, size_t cap, const char* cmd, bool ok, const char* err) {
  int n;
  if (err)
    n = snprintf(out, cap,
                 "{\"v\":1,\"node\":\"exercise-1\",\"type\":\"ack\",\"cmd\":\"%s\",\"ok\":%s,"
                 "\"err\":\"%s\"}",
                 cmd, ok ? "true" : "false", err);
  else
    n = snprintf(out, cap,
                 "{\"v\":1,\"node\":\"exercise-1\",\"type\":\"ack\",\"cmd\":\"%s\",\"ok\":%s}", cmd,
                 ok ? "true" : "false");
  return (n < 0 || (size_t)n >= cap) ? 0 : (size_t)n;
}

static const char* findValue(const char* line, const char* key) {
  char pat[20];
  if (snprintf(pat, sizeof pat, "\"%s\"", key) >= (int)sizeof pat) return NULL;
  const char* p = strstr(line, pat);
  if (!p) return NULL;
  p += strlen(pat);
  while (*p == ' ') p++;
  if (*p != ':') return NULL;
  p++;
  while (*p == ' ') p++;
  return p;
}

// Returns false when the line has no "cmd" string. Unknown command names still parse.
static bool parseCommand(const char* line, Cmd* c) {
  memset(c, 0, sizeof *c);
  const char* p = findValue(line, "cmd");
  if (!p || *p != '"') return false;
  p++;
  size_t n = 0;
  while (*p && *p != '"' && n < sizeof c->name - 1) {
    char ch = *p++;
    bool word = (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') ||
                ch == '_';
    c->name[n++] = word ? ch : '_';  // keeps the echoed name safe inside the ack JSON
  }
  c->name[n] = 0;
  if (n == 0) return false;
  if ((p = findValue(line, "angle_deg")) != NULL) {
    char* end;
    long a = strtol(p, &end, 10);
    if (end != p) {
      c->hasAngle = true;
      c->angle = a;
    }
  }
  if ((p = findValue(line, "on")) != NULL) {
    if (strncmp(p, "true", 4) == 0) {
      c->hasOn = true;
      c->on = true;
    } else if (strncmp(p, "false", 5) == 0) {
      c->hasOn = true;
      c->on = false;
    }
  }
  if ((p = findValue(line, "mass_kg")) != NULL) {
    char* end;
    double m = strtod(p, &end);
    if (end != p) {
      c->hasMass = true;
      c->mass = (float)m;
    }
  }
  return true;
}

// Two-point calibration: counts = c0 + k * F. Returns false when the points cannot give a slope.
static bool calSolve(long c1, float f1, long c2, float f2, float* k, long* c0) {
  float dF = f2 - f1;
  if (fabsf(dF) < 0.1f) return false;
  float kk = (float)(c2 - c1) / dF;
  if (!(fabsf(kk) >= 1.0f)) return false;  // also rejects NaN
  *k = kk;
  *c0 = c1 - lroundf(kk * f1);
  return true;
}

static float calValue(long counts, float k, long c0) { return (float)(counts - c0) / k; }

// Range flag for the DHT11 (datasheet ranges 0..50 C and 20..90 %RH): outside [lo, hi], or NaN,
// is out_of_range.
static uint8_t rangeFlag(float v, float lo, float hi) {
  return (v >= lo && v <= hi) ? 0 : QF_OUT_OF_RANGE;
}

// Consecutive failed sensor reads: true once three in a row have failed (as nodes/cabin_pi does).
struct FailCount {
  uint8_t n;
  bool fail() {
    if (n < 255) n++;
    return n >= 3;
  }
  void ok() { n = 0; }
};

// Load-cell flags. Uncalibrated lines are always settling; so is the first 2 s after boot.
static uint8_t loadFlags(bool calibrated, uint32_t msSinceBoot, long raw, float valN) {
  uint8_t q = 0;
  if (!calibrated || msSinceBoot < 2000) q |= QF_SETTLING;
  if (raw >= 8388607L || raw <= -8388608L) q |= QF_OUT_OF_RANGE;
  if (calibrated && fabsf(valN) > (float)CELL_CAPACITY_KG * kGravity) q |= QF_OUT_OF_RANGE;
  return q;
}

// 10 k NTC to ground under a series resistor (the common module wiring, and the Wokwi part).
// adc is 0..1023 (may be fractional after averaging). Returns false near the rails.
static bool ntcCelsius(float adc, float* c) {
  if (!(adc > 8.0f && adc < 1015.0f)) return false;
  float r = NTC_SERIES_OVER_R25 * adc / (1023.0f - adc);  // R_ntc / R25
  *c = 1.0f / (logf(r) / NTC_BETA + 1.0f / 298.15f) - 273.15f;
  return true;
}

// Settling for the NTC: first 30 s, or more than 0.1 C change over the last 30 s.
// Call once per 5 s sample: six slots span 30 s.
struct Settle30 {
  float hist[6];
  uint8_t n, head;
  bool update(float t) {
    bool settling = true;
    if (n == 6) settling = fabsf(t - hist[head]) > 0.1f;  // hist[head] is the oldest sample
    hist[head] = t;
    head = (uint8_t)((head + 1) % 6);
    if (n < 6) n++;
    return settling;
  }
};

// Peak-interval pulse estimate for a KY-039-style module. Feed it one raw ADC value about every
// 10 ms. It is an estimate from a hobby sensor, not a measurement of heart rate.
struct HrEst {
  float dc, xs, prev, env;
  uint32_t lastBeatMs, lowSinceMs;
  uint32_t iv[5];
  uint8_t nIv;
  bool primed, contact;

  void reset() { memset(this, 0, sizeof *this); }

  void push(uint16_t sample, uint32_t ms) {
    if (!primed) {
      dc = sample;
      primed = true;
      lowSinceMs = ms;
    }
    dc += ((float)sample - dc) / 128.0f;
    float x = (float)sample - dc;
    prev = xs;
    xs = 0.5f * xs + 0.5f * x;
    float a = fabsf(xs);
    env = a > env ? a : env * 0.995f;
    if (env >= HR_MIN_AMP) {
      contact = true;
      lowSinceMs = ms;
    } else if (contact && (uint32_t)(ms - lowSinceMs) > 1000) {
      contact = false;
      nIv = 0;
      lastBeatMs = 0;
    }
    if (!contact) return;
    float th = 0.5f * env;
    if (prev < th && xs >= th && (lastBeatMs == 0 || (uint32_t)(ms - lastBeatMs) >= 300)) {
      if (lastBeatMs != 0) {
        uint32_t d = ms - lastBeatMs;
        if (d <= 1500) {
          if (nIv == 5) {
            for (uint8_t i = 0; i < 4; i++) iv[i] = iv[i + 1];
            nIv = 4;
          }
          iv[nIv++] = d;
        } else {
          nIv = 0;  // a long gap: start counting intervals again
        }
      }
      lastBeatMs = ms;
    }
  }

  bool hasContact() const { return contact; }

  // Median interval in ms (0 if fewer than two intervals).
  uint32_t medianIv() const {
    if (nIv < 2) return 0;
    uint32_t t[5];
    for (uint8_t i = 0; i < nIv; i++) t[i] = iv[i];
    for (uint8_t i = 1; i < nIv; i++)
      for (uint8_t j = i; j > 0 && t[j - 1] > t[j]; j--) {
        uint32_t s = t[j];
        t[j] = t[j - 1];
        t[j - 1] = s;
      }
    return t[nIv / 2];
  }

  // Settling until five intervals agree to within 30 % of their median.
  bool settling() const {
    if (nIv < 5) return true;
    uint32_t mn = iv[0], mx = iv[0];
    for (uint8_t i = 1; i < 5; i++) {
      if (iv[i] < mn) mn = iv[i];
      if (iv[i] > mx) mx = iv[i];
    }
    return (float)(mx - mn) > 0.3f * (float)medianIv();
  }

  float bpm() const {
    uint32_t m = medianIv();
    return m ? 60000.0f / (float)m : 0.0f;
  }
};
// END PURE

// ---------------------------------------------------------------------------------------------
// Hardware part.

static const uint8_t PIN_DHT = 2, PIN_HX_DOUT = 3, PIN_HX_SCK = 4, PIN_SERVO = 6, PIN_BUZZER = 8;
static const uint8_t PIN_NTC = A0, PIN_PULSE = A1;
static const uint16_t EE_BOOT = 0, EE_K = 8, EE_C0 = 12, EE_MARK = 16;
static const uint8_t CAL_MARK = 0xA5;
static const char NODE_RIG[] = "exercise-1";
static const char NODE_CABIN[] = "cabin-1";

static uint32_t bootNo = 0, seqNo = 0, bootMs = 0;

static bool alarmOn = false, buzzerOn = false;
static uint32_t alarmStartMs = 0;

static char inBuf[64];
static uint8_t inLen = 0;
static bool inOverflow = false;

static char outBuf[168];  // longest reading line is about 135 bytes; the budget is 160

static void emit(size_t n) {
  if (n == 0) return;
  Serial.write((const uint8_t*)outBuf, n);
  Serial.write('\n');
}

static void ack(const char* cmd, bool ok, const char* err) { emit(buildAck(outBuf, sizeof outBuf, cmd, ok, err)); }

static void emitReading(const char* node, const char* ind, float val, const char* unit, const char* dev,
                        uint8_t q) {
  emit(buildReading(outBuf, sizeof outBuf, node, bootNo, ++seqNo, ind, val, unit, dev, q));
}

#if ENABLE_SERVO
static Servo servo;
#endif

#if ENABLE_HX711
static HX711 scale;
static bool calibrated = false;
static float calK = kPlaceholderK;
static long calC0 = 0;

// Calibration / tare capture: mean of 40 samples (0.5 s at 80 SPS), taken while the stream runs.
static Capture capKind = CAP_NONE;
static uint8_t capN = 0;
static long capSum = 0;
static float capMass = 0;
static bool havePoint1 = false;
static long point1Counts = 0;
static float point1Mass = 0;

static uint32_t rateWindowStart = 0, rateCount = 0;

static void loadCalibration() {
  float k;
  long c0;
  EEPROM.get(EE_K, k);
  EEPROM.get(EE_C0, c0);
  if (EEPROM.read(EE_MARK) == CAL_MARK && k == k && fabsf(k) >= 1.0f) {
    calK = k;
    calC0 = c0;
    calibrated = true;
    Serial.print(F("# cal loaded k="));
    Serial.print(calK, 4);
    Serial.print(F(" c0="));
    Serial.println(calC0);
  } else {
    Serial.println(F("# cal missing"));
  }
}

static void storeCalibration() {
  EEPROM.put(EE_K, calK);
  EEPROM.put(EE_C0, calC0);
  EEPROM.write(EE_MARK, CAL_MARK);
}

static void startCapture(Capture kind, float mass) {
  capKind = kind;
  capN = 0;
  capSum = 0;
  capMass = mass;
}

static void finishCapture() {
  long mean = capSum / 40;
  Capture kind = capKind;
  capKind = CAP_NONE;
  if (kind == CAP_TARE) {
    calC0 = mean;
    storeCalibration();
    Serial.print(F("# tare c0="));
    Serial.println(calC0);
    ack("tare", true, NULL);
    return;
  }
  if (!havePoint1) {
    havePoint1 = true;
    point1Counts = mean;
    point1Mass = capMass;
    Serial.print(F("# cal n=1 counts="));
    Serial.println(mean);
    ack("cal", true, NULL);
    return;
  }
  float k;
  long c0;
  if (!calSolve(point1Counts, point1Mass * kGravity, mean, capMass * kGravity, &k, &c0)) {
    ack("cal", false, "no_span");
    return;
  }
  calK = k;
  calC0 = c0;
  calibrated = true;
  havePoint1 = false;
  storeCalibration();
  Serial.print(F("# cal k="));
  Serial.print(calK, 4);
  Serial.print(F(" c0="));
  Serial.print(calC0);
  Serial.println(F(" n=2"));
  ack("cal", true, NULL);
}
#endif

static void handleLine(const char* line) {
  if (line[0] != '{') return;  // not a command; ignore quietly
  Cmd c;
  if (!parseCommand(line, &c)) {
    ack("", false, "bad_command");
    return;
  }
  if (strcmp(c.name, "servo") == 0) {
#if ENABLE_SERVO
    if (!c.hasAngle) {
      ack("servo", false, "missing_angle");
      return;
    }
    long a = c.angle;
    if (a < 0 || a > 180) {
      a = a < 0 ? 0 : 180;
      Serial.print(F("# servo clamped "));
      Serial.println(a);
    }
    servo.write((int)a);
    ack("servo", true, NULL);
#else
    ack("servo", false, "not_built");  // no servo on the D40 board
#endif
  } else if (strcmp(c.name, "alarm") == 0) {
    if (!c.hasOn) {
      ack("alarm", false, "missing_on");
      return;
    }
    if (c.on && !alarmOn) alarmStartMs = millis();
    alarmOn = c.on;
    ack("alarm", true, NULL);
  } else if (strcmp(c.name, "tare") == 0 || strcmp(c.name, "cal") == 0) {
#if ENABLE_HX711
    if (strcmp(c.name, "tare") == 0) {
      if (capKind != CAP_NONE)
        ack("tare", false, "busy");
      else if (!calibrated)
        ack("tare", false, "uncalibrated");
      else
        startCapture(CAP_TARE, 0);
    } else {
      if (capKind != CAP_NONE)
        ack("cal", false, "busy");
      else if (!c.hasMass || !(c.mass > 0.0f))
        ack("cal", false, "bad_mass");
      else if (havePoint1 && fabsf(c.mass - point1Mass) * kGravity < 0.1f)
        ack("cal", false, "same_mass");
      else
        startCapture(CAP_CAL, c.mass);
    }
#else
    ack(c.name, false, "not_built");  // no load cell on the D40 board
#endif
  } else {
    ack(c.name, false, "unknown");
  }
}

static void pollSerial() {
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (inLen > 0 && !inOverflow) {
        inBuf[inLen] = 0;
        handleLine(inBuf);
      } else if (inOverflow) {
        Serial.println(F("# input too long, dropped"));
      }
      inLen = 0;
      inOverflow = false;
    } else if (inLen < sizeof inBuf - 1) {
      inBuf[inLen++] = ch;
    } else {
      inOverflow = true;
    }
  }
}

#if ENABLE_HX711
static void onLoadSample(long raw) {
  rateCount++;
  if (capKind != CAP_NONE) {
    capSum += raw;
    if (++capN >= 40) finishCapture();
  }
  float val = calibrated ? calValue(raw, calK, calC0) : (float)raw / kPlaceholderK;
  uint8_t q = loadFlags(calibrated, millis() - bootMs, raw, val);
  emitReading(NODE_RIG, "load_raw", val, "N", "HX711", q);
}

static void rateDiagnostic(uint32_t now) {
  uint32_t elapsed = now - rateWindowStart;
  if (elapsed < 10000) return;
  uint32_t x10 = (uint32_t)((uint64_t)rateCount * 10000ULL / elapsed);
  Serial.print(F("# rate_sps="));
  Serial.print(x10 / 10);
  Serial.print('.');
  Serial.println(x10 % 10);
  rateWindowStart = now;
  rateCount = 0;
}
#endif

// Alarm pattern: 500 ms on, 500 ms off. The pin is touched only when the state changes, so a
// passive buzzer's tone() is not restarted on every loop.
static void updateBuzzer(uint32_t now) {
  bool on = alarmOn && (((now - alarmStartMs) / 500) % 2 == 0);
  if (on == buzzerOn) return;
  buzzerOn = on;
#if BUZZER_PASSIVE
  if (on)
    tone(PIN_BUZZER, 2000);
  else
    noTone(PIN_BUZZER);
#else
  digitalWrite(PIN_BUZZER, on ? HIGH : LOW);
#endif
}

#if ENABLE_DHT
// DHT11 on D2, cabin-1, every 5 s (the sensor allows one read per second). The library waits about
// 20 ms for the start pulse, then reads the frame with interrupts off for about 4 ms (up to 10 ms
// when no sensor answers). Serial bytes arriving inside that window are lost, so a hub command
// that overlaps it (about 0.1 % of commands) gets a bad_command or unknown ack and is not applied.
// Nothing retries it: the hub re-sends the servo and alarm state only after a reconnect.
// With the HX711 built in, about 2 samples drop per read.
static DHT dht(PIN_DHT, DHT_TYPE);
static FailCount dhtFails;
static uint32_t dhtLastMs = (uint32_t)-3000;  // first read 2 s after boot

static void dhtPoll(uint32_t now) {
  if ((uint32_t)(now - dhtLastMs) < 5000) return;
  dhtLastMs = now;
  float t = dht.readTemperature();
  float h = dht.readHumidity();  // same frame as the temperature (the library caches it for 2 s)
  if (isnan(t) || isnan(h)) {
    if (dhtFails.fail()) {  // val 0 with no_contact after three failed reads, as nodes/cabin_pi does
      emitReading(NODE_CABIN, "cabin_temp", 0, "C", "DHT11", QF_NO_CONTACT);
      emitReading(NODE_CABIN, "cabin_rh", 0, "%", "DHT11", QF_NO_CONTACT);
    }
    return;
  }
  dhtFails.ok();
  emitReading(NODE_CABIN, "cabin_temp", t, "C", "DHT11", rangeFlag(t, 0, 50));
  emitReading(NODE_CABIN, "cabin_rh", h, "%", "DHT11", rangeFlag(h, 20, 90));
}
#endif

#if ENABLE_BMP280
// BMP280 on A4/A5, cabin-1 cabin_p every 5 s, 2.5 s after the DHT11 so their lines do not bunch up.
// A read is one 6-byte I2C burst with interrupts on (under 1 ms at 100 kHz), so serial input is
// not lost; Wire's timeout keeps a stuck bus from hanging the loop.
static bmp280::Poller baro;
static bool baroStarted = false;

static void baroPoll(uint32_t now) {
  if (!baroStarted) {
    if ((uint32_t)(now - bootMs) < 4500) return;  // first probe 4.5 s after boot
    baroStarted = true;
  }
  float p = 0;
  switch (baro.poll(now, 5000, &p)) {
    case bmp280::EV_READING:
      emitReading(NODE_CABIN, "cabin_p", p, "hPa", baro.isBme280() ? "BME280" : "BMP280",
                  bmp280::inRange(p) ? 0 : QF_OUT_OF_RANGE);
      break;
    case bmp280::EV_FOUND:
      Serial.print(F("# bmp280 found addr=0x"));
      Serial.println(baro.address(), HEX);
      break;
    case bmp280::EV_MISSING:
      Serial.println(F("# bmp280 missing at 0x76 and 0x77: no cabin_p, other channels go on"));
      break;
    case bmp280::EV_LOST:
      Serial.println(F("# bmp280 lost: no cabin_p until it answers again"));
      break;
    default:
      break;
  }
}
#endif

#if ENABLE_NTC
static Settle30 ntcSettle;
static uint32_t ntcLastMs = 0;

static void ntcPoll(uint32_t now) {
  if ((uint32_t)(now - ntcLastMs) < 5000) return;
  ntcLastMs = now;
  analogRead(PIN_NTC);  // discard, lets the mux settle
  uint32_t sum = 0;
  for (uint8_t i = 0; i < 16; i++) sum += analogRead(PIN_NTC);
  float adc = (float)sum / 16.0f, t = 0;
  uint8_t q = 0;
  if (!ntcCelsius(adc, &t)) {
    emitReading(NODE_RIG, "skin_temp", 0, "C", "NTC", QF_OUT_OF_RANGE);
    return;
  }
  if (ntcSettle.update(t)) q |= QF_SETTLING;
  if (t < 30.0f) q |= QF_NO_CONTACT;  // team value, as for the other skin probes
  emitReading(NODE_RIG, "skin_temp", t, "C", "NTC", q);
}
#endif

#if ENABLE_KY039
static HrEst hr;
static uint32_t hrSampleMs = 0, hrLastMs = 2500;  // offset from the NTC publish

static void hrPoll(uint32_t now) {
  if ((uint32_t)(now - hrSampleMs) >= 10) {
    hrSampleMs = now;
    hr.push((uint16_t)analogRead(PIN_PULSE), now);
  }
  if ((uint32_t)(now - hrLastMs) < 5000) return;
  hrLastMs = now;
  if (!hr.hasContact()) {
    emitReading(NODE_RIG, "hr", 0, "bpm", "KY039", QF_NO_CONTACT);  // val 0 with no_contact, per the contract notes
    return;
  }
  emitReading(NODE_RIG, "hr", hr.bpm(), "bpm", "KY039", hr.settling() ? QF_SETTLING : 0);
}
#endif

void setup() {
  Serial.begin(250000);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);  // after every reset the alarm is off
#if ENABLE_SERVO
  servo.attach(PIN_SERVO);
  servo.write(0);  // and the dial is at 0
#endif

  EEPROM.get(EE_BOOT, bootNo);
  if (bootNo == 0xFFFFFFFFUL) bootNo = 0;  // fresh EEPROM
  bootNo++;
  EEPROM.put(EE_BOOT, bootNo);

  Serial.println();  // ends any partial line left on the wire
  Serial.print(F("# exercise-1 boot="));
  Serial.println(bootNo);
#if ENABLE_HX711
  loadCalibration();
#endif
  Serial.print(F("# channels dht="));
  Serial.print(ENABLE_DHT ? F("on") : F("off"));
  Serial.print(F(" hx711="));
  Serial.print(ENABLE_HX711 ? F("on") : F("off"));
  Serial.print(F(" servo="));
  Serial.print(ENABLE_SERVO ? F("on") : F("off"));
  Serial.print(F(" ntc="));
  Serial.print(ENABLE_NTC ? F("on") : F("off"));
  Serial.print(F(" ky039="));
  Serial.print(ENABLE_KY039 ? F("on") : F("off"));
  Serial.print(F(" bmp280="));
  Serial.print(ENABLE_BMP280 ? F("on") : F("off"));
  Serial.print(F(" buzzer="));
  Serial.println(BUZZER_PASSIVE ? F("passive") : F("active"));

#if ENABLE_HX711
  scale.begin(PIN_HX_DOUT, PIN_HX_SCK);
#endif
#if ENABLE_DHT
  dht.begin();
#endif
#if ENABLE_BMP280
  Wire.begin();
  digitalWrite(SDA, LOW);  // Wire.begin() turned the AVR's internal pull-ups (to 5 V) on: switch them
  digitalWrite(SCL, LOW);  // off, so the 3.3 V module's pull-ups alone set the bus high level
  Wire.setWireTimeout(25000, true);  // 25 ms, then reset the TWI: a stuck bus never hangs the board
#endif
#if ENABLE_KY039
  hr.reset();
#endif
  bootMs = millis();
#if ENABLE_HX711
  rateWindowStart = bootMs;
#endif
}

void loop() {
  uint32_t now = millis();
#if ENABLE_HX711
  if (scale.is_ready()) onLoadSample(scale.read());  // the HX711 read has priority
#endif
  pollSerial();
  updateBuzzer(now);
#if ENABLE_HX711
  rateDiagnostic(now);
#endif
#if ENABLE_DHT
  dhtPoll(now);
#endif
#if ENABLE_NTC
  ntcPoll(now);
#endif
#if ENABLE_KY039
  hrPoll(now);
#endif
#if ENABLE_BMP280
  baroPoll(now);
#endif
}
