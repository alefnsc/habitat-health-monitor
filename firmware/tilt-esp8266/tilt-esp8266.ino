// tilt node (decision D39): a sealed KY-017 mercury tilt switch on D5, published as ind "tilt".
//   Value 1 = switch tripped (weight tilted past the trip angle), 0 = released. Raw state, no angle.
//   One reading on every debounced change, plus a heartbeat with the current state every 10 s.
// Educational prototype. Readings go to habitat/v1/r/tilt-1 through HabitatNode.
//
// Board: NodeMCU Amica (esp8266:esp8266:nodemcuv2). Pin: D5 (GPIO14), INPUT_PULLUP.
// Keep D1/D2 free (I2C for a later MPU6050) and D3, D4, D8 free (boot pins). USB power from the hub.
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

#ifndef TILT_ACTIVE_LOW
#define TILT_ACTIVE_LOW 1  // tripped = pin pulled LOW; if the pod reads 1 at rest, turn it around
#endif

// BEGIN PURE
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

static const uint32_t kDebounceMs = 30;
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

void setup() {
  Serial.begin(115200);
  Serial.println();
  pinMode(PIN_TILT, INPUT_PULLUP);
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
  delay(2);
}
