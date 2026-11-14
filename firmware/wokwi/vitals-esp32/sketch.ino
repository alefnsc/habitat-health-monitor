// vitals node (F11, F12 as MLX90614, F13a; decision D37): one battery-powered board, one 3.3 V I2C bus.
//   MAX30102 0x57  hr every 1 s, spo2 every 4 s (estimates from the Maxim reference algorithm)
//   MLX90614 0x5A  skin_temp every 2 s, non-contact object temperature (hobby estimate)
//   MPU6050  0x68  motion every 1 s, and the motion bit on hr/spo2
// Educational prototype, not a medical device. Readings go to habitat/v1/r/vitals-1 through HabitatNode.
//
// Boards: NodeMCU Amica (esp8266:esp8266:nodemcuv2) is the real node; esp32:esp32:esp32 also builds.
// Pins: ESP8266 SDA D2 (GPIO4), SCL D1 (GPIO5); keep D3, D4 and D8 free (boot pins). ESP32: default Wire pins.
// Many MAX30102 boards pull SDA/SCL up to 1.8 V: move the jumper to 3.3 V. Battery power only (safety checklist).
//
// secrets.h present   -> readings are queued to HabitatNode and published over Wi-Fi/MQTT.
// secrets.h missing   -> serial-only mode: the same contract-v1 lines are printed to Serial (used by the
//                        Wokwi twin, which has no broker). The banner says which mode is running.
//
// The block between BEGIN PURE and END PURE is plain C++ with no Arduino calls. It is extracted and compiled
// on the host by firmware/vitals-esp32/test/run_host_tests.sh.

#include <Wire.h>

#include <MAX30105.h>
#include <spo2_algorithm.h>

#if __has_include("secrets.h")
#include "secrets.h"
#include <HabitatNode.h>
#define VITALS_MQTT 1
#else
#define VITALS_MQTT 0
#endif

#ifndef MOTION_GATE_G
#define MOTION_GATE_G 0.05f  // team value (spec addition 8), tune on the bench
#endif
#ifndef MLX_CHECK_PEC
#define MLX_CHECK_PEC 1  // verify the SMBus packet error code on every MLX90614 read
#endif

// BEGIN PURE
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Flag bits, same order as ReadingFormat.h.
static const uint8_t QF_MOTION = 1 << 0;
static const uint8_t QF_NO_CONTACT = 1 << 1;
static const uint8_t QF_SETTLING = 1 << 2;
static const uint8_t QF_OUT_OF_RANGE = 1 << 4;

enum VitalInd : uint8_t { VI_HR, VI_SPO2, VI_SKIN_TEMP, VI_MOTION };
static const char* const kIndName[4] = {"hr", "spo2", "skin_temp", "motion"};
static const char* const kIndUnit[4] = {"bpm", "%", "C", "g"};
static const uint8_t kIndDecimals[4] = {0, 0, 2, 3};  // as ReadingFormat.cpp

static const uint32_t kNoContactIr = 50000;  // mean IR below this means no finger (SparkFun Example5)
static const uint16_t kBlockSamples = 25;    // 1 s at 25 effective samples/s
static const uint16_t kWindowSamples = 100;  // 4 s window for the Maxim algorithm
static const uint16_t kSettleSamples = 100;  // first 4 s after contact

// Finger detection and the settling counter. Feed it one mean-IR value per 25-sample block.
struct ContactTracker {
  uint32_t since;  // samples since contact was detected, 0 while there is none
  bool contact;
  bool block(uint32_t meanIr) {
    contact = meanIr >= kNoContactIr;
    since = contact ? since + kBlockSamples : 0;
    return contact;
  }
  bool settling() const { return contact && since <= kSettleSamples; }
};

// skin_temp flags: no_contact below 30 C, out_of_range outside the object range, settling while the
// value moved more than 0.1 C in the last 30 s (15 samples at 2 s).
struct SkinFlags {
  float hist[15];
  uint8_t n, head;
  uint8_t update(float t) {
    uint8_t q = 0;
    bool settling = true;
    if (n == 15) settling = fabsf(t - hist[head]) > 0.1f;  // hist[head] is the sample 30 s ago
    hist[head] = t;
    head = (uint8_t)((head + 1) % 15);
    if (n < 15) n++;
    if (settling) q |= QF_SETTLING;
    if (t < 30.0f) q |= QF_NO_CONTACT;
    if (t < -70.0f || t > 380.0f) q |= QF_OUT_OF_RANGE;
    return q;
  }
};

struct MotionRms {
  float sumSq;
  uint8_t n;
  // Returns true when a 1 s value is ready in *rms.
  bool push(int16_t ax, int16_t ay, int16_t az, float* rms) {
    float x = (float)ax / 16384.0f, y = (float)ay / 16384.0f, z = (float)az / 16384.0f;  // +-2 g range
    float dyn = fabsf(sqrtf(x * x + y * y + z * z) - 1.0f);
    sumSq += dyn * dyn;
    if (++n < 50) return false;
    *rms = sqrtf(sumSq / 50.0f);
    sumSq = 0;
    n = 0;
    return true;
  }
};

// The motion bit goes on hr/spo2 computed from a 4 s window that overlaps any second above the threshold.
struct MotionGate {
  bool recent[4];
  uint8_t head;
  void push(float rms, float threshold) {
    recent[head] = rms > threshold;
    head = (uint8_t)((head + 1) % 4);
  }
  bool active() const { return recent[0] || recent[1] || recent[2] || recent[3]; }
};


// Contract-v1 line for the serial-only mode. Returns length, 0 if it does not fit.
static size_t fmtLine(char* out, size_t cap, uint32_t boot, uint32_t seq, uint32_t age_ms, uint8_t ind,
                      float val, const char* dev, uint8_t q) {
  if (ind > VI_MOTION || !(val == val)) return 0;
  static const char* const names[5] = {"motion", "no_contact", "settling", "leads_off", "out_of_range"};
  char flags[64];
  size_t fp = 0;
  if ((q & 0x1F) == 0) {
    snprintf(flags, sizeof flags, "\"ok\"");
  } else {
    flags[0] = 0;
    for (uint8_t i = 0; i < 5; i++) {
      if (!(q & (1 << i))) continue;
      int n = snprintf(flags + fp, sizeof flags - fp, "%s\"%s\"", fp ? "," : "", names[i]);
      if (n < 0 || (size_t)n >= sizeof flags - fp) return 0;
      fp += (size_t)n;
    }
  }
  int n = snprintf(out, cap,
                   "{\"v\":1,\"node\":\"vitals-1\",\"boot\":%lu,\"seq\":%lu,\"age_ms\":%lu,\"ind\":\"%s\","
                   "\"val\":%.*f,\"unit\":\"%s\",\"src\":\"hobby\",\"dev\":\"%s\",\"q\":[%s]}",
                   (unsigned long)boot, (unsigned long)seq, (unsigned long)age_ms, kIndName[ind],
                   (int)kIndDecimals[ind], (double)val, kIndUnit[ind], dev, flags);
  return (n < 0 || (size_t)n >= cap) ? 0 : (size_t)n;
}


// Flags for hr and spo2. With no contact the result is only no_contact.
static uint8_t vitalFlags(const ContactTracker& c, bool motion) {
  if (!c.contact) return QF_NO_CONTACT;
  uint8_t q = 0;
  if (c.settling()) q |= QF_SETTLING;
  if (motion) q |= QF_MOTION;
  return q;
}

// ---- MLX90614 (SMBus 0x5A). RAM 0x07 is the object temperature, 0.02 K per count. ----

// SMBus CRC-8 (polynomial x^8 + x^2 + x + 1, init 0).
static uint8_t smbusCrc8(const uint8_t* d, size_t n) {
  uint8_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    crc ^= d[i];
    for (uint8_t b = 0; b < 8; b++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

// Decode a read-word reply (lsb, msb, pec) for command cmd at 7-bit address addr.
// Returns false on a bad PEC (when checkPec) or when the sensor flags an error (MSB bit 7).
static bool mlxDecode(uint8_t addr, uint8_t cmd, uint8_t lsb, uint8_t msb, uint8_t pec, bool checkPec,
                      float* celsius) {
  if (checkPec) {
    uint8_t buf[5] = {(uint8_t)(addr << 1), cmd, (uint8_t)((addr << 1) | 1), lsb, msb};
    if (smbusCrc8(buf, 5) != pec) return false;
  }
  if (msb & 0x80) return false;  // error flag: the raw word is not a temperature
  uint16_t raw = (uint16_t)((msb << 8) | lsb);
  *celsius = (float)raw * 0.02f - 273.15f;
  return true;
}


// ---- MPU6050: dynamic acceleration, RMS over 50 samples (1 s at 50 Hz), gating over 4 s. ----


// END PURE

// ---------------------------------------------------------------------------------------------
// Hardware part.

#if defined(ESP8266)
static const int PIN_SDA = 4;  // D2 on the NodeMCU Amica
static const int PIN_SCL = 5;  // D1
#endif

static const uint8_t ADDR_MAX = 0x57, ADDR_MLX = 0x5A, ADDR_MPU = 0x68;

#if VITALS_MQTT
static HabitatNode node;
static_assert(habitat::Q_MOTION == QF_MOTION && habitat::Q_NO_CONTACT == QF_NO_CONTACT &&
                  habitat::Q_SETTLING == QF_SETTLING && habitat::Q_OUT_OF_RANGE == QF_OUT_OF_RANGE,
              "flag bits must match ReadingFormat.h");
#else
static uint32_t serialBoot = 1, serialSeq = 0;
#endif

static void emit(uint8_t ind, float val, const char* dev, uint8_t q) {
#if VITALS_MQTT
  static const uint8_t indMap[4] = {habitat::IND_HR, habitat::IND_SPO2, habitat::IND_SKIN_TEMP,
                                    habitat::IND_MOTION};
  uint8_t d = habitat::DEV_MAX30102;
  if (!strcmp(dev, "MLX90614")) d = habitat::DEV_MLX90614;
  if (!strcmp(dev, "MPU6050")) d = habitat::DEV_MPU6050;
  node.queue(indMap[ind], val, d, q);
#else
  char buf[200];
  size_t n = fmtLine(buf, sizeof buf, serialBoot, ++serialSeq, 0, ind, val, dev, q);
  if (n) Serial.println(buf);
#endif
}

static MAX30105 maxSensor;
static bool maxOk = false;
static ContactTracker contact;
static MotionGate gate;
static uint32_t irWin[kWindowSamples], redWin[kWindowSamples];
static uint16_t winFill = 0;
static uint32_t blkIr[kBlockSamples], blkRed[kBlockSamples];
static uint16_t blkN = 0;
static uint8_t runCount = 0;
static uint32_t algoInvalid = 0, lastInvalidDiag = 0, lastNoContactMs = 0, lastSenseMs = 0;

static bool mpuOk = false;
static MotionRms motionRms;
static uint32_t lastMpuMs = 0;

static bool mlxMissingReported = false;
static uint8_t mlxFails = 0;
static SkinFlags skinFlags;
static uint32_t lastMlxMs = 0;

static void resetWindow() {
  winFill = 0;
  blkN = 0;
  runCount = 0;
}

static void runAlgorithm() {
  int32_t spo2 = 0, hr = 0;
  int8_t spo2Valid = 0, hrValid = 0;
  maxim_heart_rate_and_oxygen_saturation(irWin, kWindowSamples, redWin, &spo2, &spo2Valid, &hr, &hrValid);
  uint8_t q = vitalFlags(contact, gate.active());
  if (hrValid) emit(VI_HR, (float)hr, "MAX30102", q);
  else algoInvalid++;
  if (++runCount >= 4) {  // SpO2 every 4th run (4 s)
    runCount = 0;
    if (spo2Valid) emit(VI_SPO2, (float)spo2, "MAX30102", q);
  }
}

static void onBlock() {
  uint64_t sum = 0;
  for (uint16_t i = 0; i < kBlockSamples; i++) sum += blkIr[i];
  bool had = contact.contact;
  contact.block((uint32_t)(sum / kBlockSamples));
  if (!contact.contact) {
    if (had) Serial.printf("# max3010x ir=%lu no_contact\n", (unsigned long)(sum / kBlockSamples));
    resetWindow();
    return;
  }
  if (winFill < kWindowSamples) {
    memcpy(irWin + winFill, blkIr, sizeof blkIr);
    memcpy(redWin + winFill, blkRed, sizeof blkRed);
    winFill += kBlockSamples;
    if (winFill < kWindowSamples) return;
  } else {
    memmove(irWin, irWin + kBlockSamples, (kWindowSamples - kBlockSamples) * sizeof irWin[0]);
    memmove(redWin, redWin + kBlockSamples, (kWindowSamples - kBlockSamples) * sizeof redWin[0]);
    memcpy(irWin + kWindowSamples - kBlockSamples, blkIr, sizeof blkIr);
    memcpy(redWin + kWindowSamples - kBlockSamples, blkRed, sizeof blkRed);
  }
  runAlgorithm();
}

static void senseMax(uint32_t now) {
  if (!maxOk) return;
  // The sensor FIFO holds 32 samples (1.28 s). A longer pause (Wi-Fi reconnect on a single core) loses data:
  // start the window again rather than run the algorithm on a gap.
  if (lastSenseMs && now - lastSenseMs > 800) {
    Serial.printf("# fifo gap ms=%lu\n", (unsigned long)(now - lastSenseMs));
    resetWindow();
    contact.since = 0;
  }
  lastSenseMs = now;
  maxSensor.check();
  while (maxSensor.available()) {
    blkRed[blkN] = maxSensor.getFIFORed();
    blkIr[blkN] = maxSensor.getFIFOIR();
    maxSensor.nextSample();
    if (++blkN >= kBlockSamples) {
      blkN = 0;
      onBlock();
    }
  }
  if (!contact.contact && now - lastNoContactMs >= 5000) {  // hr with val 0 every 5 s while no finger
    lastNoContactMs = now;
    emit(VI_HR, 0.0f, "MAX30102", QF_NO_CONTACT);
  }
  if (now - lastInvalidDiag >= 10000) {
    lastInvalidDiag = now;
    Serial.printf("# algo invalid=%lu\n", (unsigned long)algoInvalid);
  }
}

static bool mpuRead(int16_t* a) {
  Wire.beginTransmission(ADDR_MPU);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)ADDR_MPU, 6) != 6) return false;
  for (int i = 0; i < 3; i++) {
    uint8_t hi = Wire.read();
    uint8_t lo = Wire.read();
    a[i] = (int16_t)((hi << 8) | lo);
  }
  return true;
}

static void senseMpu(uint32_t now) {
  if (!mpuOk || now - lastMpuMs < 20) return;  // 50 Hz
  lastMpuMs = now;
  int16_t a[3];
  float rms;
  if (mpuRead(a) && motionRms.push(a[0], a[1], a[2], &rms)) {
    gate.push(rms, MOTION_GATE_G);
    emit(VI_MOTION, rms, "MPU6050", 0);
  }
}

static bool mlxRead(float* celsius) {
  Wire.beginTransmission(ADDR_MLX);
  Wire.write(0x07);  // RAM address 0x07: object temperature 1
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)ADDR_MLX, 3) != 3) return false;
  uint8_t lsb = Wire.read(), msb = Wire.read(), pec = Wire.read();
  return mlxDecode(ADDR_MLX, 0x07, lsb, msb, pec, MLX_CHECK_PEC, celsius);
}

static void senseMlx(uint32_t now) {
  if (now - lastMlxMs < 2000) return;
  lastMlxMs = now;
  float c;
  if (!mlxRead(&c)) {
    if (++mlxFails >= 3 && !mlxMissingReported) {
      mlxMissingReported = true;
      Serial.println(F("# mlx90614 missing or unreadable"));
    }
    return;
  }
  mlxFails = 0;
  mlxMissingReported = false;
  emit(VI_SKIN_TEMP, c, "MLX90614", skinFlags.update(c));
}

static bool probe(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

#if VITALS_MQTT && defined(ESP32)
static void nodeTask(void*) {
  for (;;) {
    node.loop();
    vTaskDelay(1);
  }
}
#endif

void setup() {
  Serial.begin(115200);
  Serial.println();
#if defined(ESP8266)
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClockStretchLimit(4000);  // the MLX90614 may stretch the clock
#else
  Wire.begin();
#endif
  Wire.setClock(100000);  // the MLX90614 SMBus limit; the MAX30102 and MPU6050 run fine at 100 kHz

#if VITALS_MQTT
  node.begin("vitals-1");
#else
  Serial.println(F("# vitals-1 serial-only mode (no secrets.h)"));
#endif

  maxOk = maxSensor.begin(Wire, I2C_SPEED_STANDARD, ADDR_MAX);
  if (maxOk) {
    maxSensor.setup(60, 4, 2, 100, 411, 4096);  // SparkFun Example8: 25 effective samples/s
    Serial.println(F("# max3010x found addr=0x57"));
  } else {
    Serial.println(F("# max3010x missing"));
  }

  mpuOk = probe(ADDR_MPU);
  if (mpuOk) {
    Wire.beginTransmission(ADDR_MPU);
    Wire.write(0x6B);  // PWR_MGMT_1: wake
    Wire.write(0x00);
    Wire.endTransmission();
    Wire.beginTransmission(ADDR_MPU);
    Wire.write(0x1C);  // ACCEL_CONFIG: +-2 g
    Wire.write(0x00);
    Wire.endTransmission();
    Wire.beginTransmission(ADDR_MPU);
    Wire.write(0x75);  // WHO_AM_I: logged, any value accepted (clones differ)
    Wire.endTransmission(false);
    Wire.requestFrom((int)ADDR_MPU, 1);
    Serial.printf("# mpu6050 addr=0x68 who_am_i=0x%02X\n", Wire.available() ? Wire.read() : 0);
  } else {
    Serial.println(F("# mpu6050 missing"));
  }

  if (probe(ADDR_MLX)) Serial.println(F("# mlx90614 found addr=0x5A"));
  else Serial.println(F("# mlx90614 not answering yet"));

#if VITALS_MQTT && defined(ESP32)
  xTaskCreatePinnedToCore(nodeTask, "habitat", 8192, nullptr, 1, nullptr, 0);  // core 0; sensing stays on core 1
#endif
}

void loop() {
  uint32_t now = millis();
  senseMax(now);
  senseMpu(now);
  senseMlx(now);
#if VITALS_MQTT && defined(ESP8266)
  node.loop();  // single core: a QoS 1 wait or reconnect attempt can pause sensing (see "fifo gap")
#endif
#if !defined(ESP8266) && !VITALS_MQTT
  delay(1);
#endif
}
