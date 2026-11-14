// exercise-uno: exercise rig on an Arduino Uno (F14, F15, F16, plus the D35 analog channels).
//
// Educational prototype, not a medical device. Readings from hobby sensors are estimates.
//
// Link: USB serial, 250000 baud 8N1. One contract-v1 reading per line (plain Serial output, no JSON
// library on the Uno). Lines starting with "# " are diagnostics. Command lines (D7) come in on the
// same port, one JSON object per line; every command is answered with one ack line.
//
// Pins: HX711 DOUT D3, SCK D4 | servo signal D6 | buzzer D8 | NTC out A0 | pulse module out A1.
// The HX711 RATE pin must be tied to DVDD for 80 SPS (see docs/wiring/exercise-uno.md).
//
// Optional channels (compile-time flags, default on because the D35 rig has both modules; build
// with -DENABLE_NTC=0 and/or -DENABLE_KY039=0 when a module is not wired, so a floating analog pin
// never publishes numbers):
//   arduino-cli compile --fqbn arduino:avr:uno --build-property "build.extra_flags=-DENABLE_NTC=0" ...
//
// The block between BEGIN PURE and END PURE is plain C++ with no Arduino calls. It is extracted and
// compiled on the host by firmware/exercise-uno/test/run_host_tests.sh.

#include <EEPROM.h>
#include <HX711.h>
#include <Servo.h>

#ifndef ENABLE_NTC
#define ENABLE_NTC 1
#endif
#ifndef ENABLE_KY039
#define ENABLE_KY039 1
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
static size_t buildReading(char* out, size_t cap, uint32_t boot, uint32_t seq, const char* ind,
                           float val, const char* unit, const char* dev, uint8_t q) {
  int n = snprintf(out, cap,
                   "{\"v\":1,\"node\":\"exercise-1\",\"boot\":%lu,\"seq\":%lu,\"age_ms\":0,"
                   "\"ind\":\"%s\",\"val\":",
                   (unsigned long)boot, (unsigned long)seq, ind);
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

static const uint8_t PIN_HX_DOUT = 3, PIN_HX_SCK = 4, PIN_SERVO = 6, PIN_BUZZER = 8;
static const uint8_t PIN_NTC = A0, PIN_PULSE = A1;
static const uint16_t EE_BOOT = 0, EE_K = 8, EE_C0 = 12, EE_MARK = 16;
static const uint8_t CAL_MARK = 0xA5;

static HX711 scale;
static Servo servo;

static uint32_t bootNo = 0, seqNo = 0, bootMs = 0;
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

static bool alarmOn = false;
static uint32_t alarmStartMs = 0;

static uint32_t rateWindowStart = 0, rateCount = 0;

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

static void emitReading(const char* ind, float val, const char* unit, const char* dev, uint8_t q) {
  emit(buildReading(outBuf, sizeof outBuf, bootNo, ++seqNo, ind, val, unit, dev, q));
}

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

static void handleLine(const char* line) {
  if (line[0] != '{') return;  // not a command; ignore quietly
  Cmd c;
  if (!parseCommand(line, &c)) {
    ack("", false, "bad_command");
    return;
  }
  if (strcmp(c.name, "servo") == 0) {
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
  } else if (strcmp(c.name, "alarm") == 0) {
    if (!c.hasOn) {
      ack("alarm", false, "missing_on");
      return;
    }
    if (c.on && !alarmOn) alarmStartMs = millis();
    alarmOn = c.on;
    ack("alarm", true, NULL);
  } else if (strcmp(c.name, "tare") == 0) {
    if (capKind != CAP_NONE)
      ack("tare", false, "busy");
    else if (!calibrated)
      ack("tare", false, "uncalibrated");
    else
      startCapture(CAP_TARE, 0);
  } else if (strcmp(c.name, "cal") == 0) {
    if (capKind != CAP_NONE)
      ack("cal", false, "busy");
    else if (!c.hasMass || !(c.mass > 0.0f))
      ack("cal", false, "bad_mass");
    else if (havePoint1 && fabsf(c.mass - point1Mass) * kGravity < 0.1f)
      ack("cal", false, "same_mass");
    else
      startCapture(CAP_CAL, c.mass);
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

static void onLoadSample(long raw) {
  rateCount++;
  if (capKind != CAP_NONE) {
    capSum += raw;
    if (++capN >= 40) finishCapture();
  }
  float val = calibrated ? calValue(raw, calK, calC0) : (float)raw / kPlaceholderK;
  uint8_t q = loadFlags(calibrated, millis() - bootMs, raw, val);
  emitReading("load_raw", val, "N", "HX711", q);
}

static void updateBuzzer(uint32_t now) {
  bool on = alarmOn && (((now - alarmStartMs) / 500) % 2 == 0);
  digitalWrite(PIN_BUZZER, on ? HIGH : LOW);
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
    emitReading("skin_temp", 0, "C", "NTC", QF_OUT_OF_RANGE);
    return;
  }
  if (ntcSettle.update(t)) q |= QF_SETTLING;
  if (t < 30.0f) q |= QF_NO_CONTACT;  // team value, as for the other skin probes
  emitReading("skin_temp", t, "C", "NTC", q);
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
    emitReading("hr", 0, "bpm", "KY039", QF_NO_CONTACT);  // val 0 with no_contact, per the contract notes
    return;
  }
  emitReading("hr", hr.bpm(), "bpm", "KY039", hr.settling() ? QF_SETTLING : 0);
}
#endif

void setup() {
  Serial.begin(250000);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  servo.attach(PIN_SERVO);
  servo.write(0);  // after every reset the dial is at 0 and the alarm is off

  EEPROM.get(EE_BOOT, bootNo);
  if (bootNo == 0xFFFFFFFFUL) bootNo = 0;  // fresh EEPROM
  bootNo++;
  EEPROM.put(EE_BOOT, bootNo);

  Serial.println();  // ends any partial line left on the wire
  Serial.print(F("# exercise-1 boot="));
  Serial.println(bootNo);
  loadCalibration();
  Serial.print(F("# channels ntc="));
  Serial.print(ENABLE_NTC ? F("on") : F("off"));
  Serial.print(F(" ky039="));
  Serial.println(ENABLE_KY039 ? F("on") : F("off"));

  scale.begin(PIN_HX_DOUT, PIN_HX_SCK);
#if ENABLE_KY039
  hr.reset();
#endif
  bootMs = millis();
  rateWindowStart = bootMs;
}

void loop() {
  uint32_t now = millis();
  if (scale.is_ready()) onLoadSample(scale.read());  // the HX711 read has priority
  pollSerial();
  updateBuzzer(now);
  rateDiagnostic(now);
#if ENABLE_NTC
  ntcPoll(now);
#endif
#if ENABLE_KY039
  hrPoll(now);
#endif
}
