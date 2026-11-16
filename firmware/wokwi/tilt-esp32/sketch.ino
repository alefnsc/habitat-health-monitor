// tilt node (decision D39): a sealed KY-017 mercury tilt switch on D5, published as ind "tilt".
//   Value 1 = switch tripped (weight tilted past the trip angle), 0 = released. Raw state, no angle.
//   One reading on every debounced change, plus a heartbeat with the current state every 10 s.
// Educational prototype. Readings go to habitat/v1/r/tilt-1 through HabitatNode.
//
// Board: NodeMCU Amica (esp8266:esp8266:nodemcuv2). Pin: D5 (GPIO14), INPUT_PULLUP.
// BMP280 (cabin_p as tilt-1, every 10 s): SDA D2 (GPIO4), SCL D1 (GPIO5), VCC on 3V3, CSB and SDO open (0x76).
//   It builds in when bmp280_lite.h sits next to this file (firmware/bmp280/sync.sh copies it); the Wokwi
//   twin has no copy and builds without it. A missing module is reported once and the tilt channel goes on.
// Keep D3, D4, D8 free (boot pins). An MPU6050 could share the D1/D2 bus later.
// Power (D40): a cell pack, so the pod on the weight has no cable. 4 x Ni-MH AA on VIN and GND (chosen),
// or 2 x alkaline AA/AAA on 3V3 and GND. Never 2 cells on VIN, never 3+ cells on 3V3, no CR2032.
// The KY-017 stays on 3V3. Rules and runtimes: firmware/tilt-esp8266/README.md.
// The Wokwi twin (firmware/wokwi/tilt-esp32) runs this same file on an ESP32 stand-in, serial-only.
// The capsule holds mercury: sealed pod, adult team members only (docs/safety-checklist.md).
//
// secrets.h present -> readings are queued to HabitatNode and published over Wi-Fi/MQTT.
// secrets.h missing -> serial-only mode: the same contract-v1 lines are printed to Serial.
// The block between BEGIN PURE and END PURE is plain C++ with no Arduino calls. It is extracted and
// compiled on the host by firmware/tilt-esp8266/test/run_host_tests.sh.

#if __has_include("secrets.h")
#include "secrets.h"
#include <HabitatNode.h>
#define TILT_MQTT 1
#else
#define TILT_MQTT 0
#endif

#if __has_include("bmp280_lite.h")
#include "bmp280_lite.h"
#define TILT_BMP280 1
#else
#define TILT_BMP280 0
#endif

#ifndef TILT_ACTIVE_LOW
#define TILT_ACTIVE_LOW 1  // tripped = pin pulled LOW; if the pod reads 1 at rest, turn it around
#endif

// BEGIN PURE
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

static const uint32_t kDebounceMs = 200;  // mercury bounces up to ~150 ms (bench 14/11)
static const uint32_t kHeartbeatMs = 10000;

// A new level is accepted only after it has held for kDebounceMs.
struct Debouncer {
  uint8_t stable = 0;     // accepted level
  uint8_t candidate = 0;  // last raw level seen
  uint32_t since = 0;     // when the candidate was first seen
  bool started = false;
  // Returns true when the accepted level changes.
  bool feed(uint8_t raw, uint32_t now_ms) {
    if (!started) {
      started = true;
      stable = candidate = raw;
      since = now_ms;
      return false;
    }
    if (raw != candidate) {
      candidate = raw;
      since = now_ms;
      return false;
    }
    if (candidate != stable && (uint32_t)(now_ms - since) >= kDebounceMs) {
      stable = candidate;
      return true;
    }
    return false;
  }
};

// True when kHeartbeatMs have passed since the last publish (unsigned, so millis() may wrap).
static inline bool heartbeatDue(uint32_t last_ms, uint32_t now_ms) {
  return (uint32_t)(now_ms - last_ms) >= kHeartbeatMs;
}

// Serial-only contract-v1 line. Returns bytes written, or 0 if it does not fit.
static inline size_t fmtTiltLine(char* out, size_t cap, uint32_t boot, uint32_t seq, uint8_t val) {
  int n = snprintf(out, cap,
                   "{\"v\":1,\"node\":\"tilt-1\",\"boot\":%lu,\"seq\":%lu,\"age_ms\":0,"
                   "\"ind\":\"tilt\",\"val\":%u,\"unit\":\"state\",\"src\":\"hobby\","
                   "\"dev\":\"KY017\",\"q\":[\"ok\"]}",
                   (unsigned long)boot, (unsigned long)seq, (unsigned)val);
  return (n > 0 && (size_t)n < cap) ? (size_t)n : 0;
}
// END PURE

// ---------------------------------------------------------------------------------------------
// Hardware part.

static const int PIN_TILT = 14;  // D5 on the NodeMCU Amica

#if TILT_MQTT
static HabitatNode node;
#else
static uint32_t serialBoot = 1, serialSeq = 0;
#endif

static Debouncer deb;
static uint32_t lastPublish = 0;

static uint8_t readRaw() {
  int level = digitalRead(PIN_TILT);
  if (TILT_ACTIVE_LOW) return level == LOW ? 1 : 0;
  return level == HIGH ? 1 : 0;
}

static void publish(uint8_t val) {
#if TILT_MQTT
  node.queue(habitat::IND_TILT, (float)val, habitat::DEV_KY017, 0);
#else
  char buf[200];
  size_t n = fmtTiltLine(buf, sizeof buf, serialBoot, ++serialSeq, val);
  if (n) Serial.println(buf);
#endif
  lastPublish = millis();
}

#if TILT_BMP280
static bmp280::Poller baro;

static void baroPoll(uint32_t now) {
  float p = 0;
  switch (baro.poll(now, 10000, &p)) {
    case bmp280::EV_READING:
#if TILT_MQTT
      node.queue(habitat::IND_CABIN_P, p, habitat::DEV_BMP280,
                 bmp280::inRange(p) ? 0 : habitat::Q_OUT_OF_RANGE);
#else
      Serial.print(F("# bmp280 cabin_p hPa="));
      Serial.println(p, 2);
#endif
      break;
    case bmp280::EV_FOUND:
      Serial.print(F("# bmp280 found addr=0x"));
      Serial.println(baro.address(), HEX);
      break;
    case bmp280::EV_MISSING:
      Serial.println(F("# bmp280 missing at 0x76 and 0x77: no cabin_p, tilt goes on"));
      break;
    case bmp280::EV_LOST:
      Serial.println(F("# bmp280 lost: no cabin_p until it answers again"));
      break;
    default:
      break;
  }
}
#endif

void setup() {
  Serial.begin(115200);
  Serial.println();
  pinMode(PIN_TILT, INPUT_PULLUP);
#if TILT_BMP280
  Wire.begin();  // NodeMCU default pins: SDA D2 (GPIO4), SCL D1 (GPIO5)
#endif
#if TILT_MQTT
  node.begin("tilt-1");
#else
  Serial.println(F("# tilt-1 serial-only mode (no secrets.h)"));
#endif
  deb.feed(readRaw(), millis());
  publish(deb.stable);
}

void loop() {
#if TILT_MQTT
  node.loop();
#endif
  uint32_t now = millis();
  if (deb.feed(readRaw(), now) || heartbeatDue(lastPublish, now)) publish(deb.stable);
#if TILT_BMP280
  baroPoll(now);
#endif
  delay(2);
}
