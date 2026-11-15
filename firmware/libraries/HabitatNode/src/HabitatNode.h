// Node runtime shared by the ESP sketches: boot counter, sequence numbers, a
// 32-entry ring of unsent readings, and an MQTT link with a retained last will.
// ESP8266 and ESP32 only. Include the sketch's secrets.h BEFORE this header if
// you want the one-argument begin(node_id); otherwise call beginWith().
#pragma once

#include <Arduino.h>
#include <MQTT.h>

#include "ReadingFormat.h"
#include "RingBuffer.h"

#if defined(ARDUINO_ARCH_ESP32)
#include <WiFi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#else
#include <ESP8266WiFi.h>
#endif

namespace habitat {
// Reads, increments and persists the boot counter. First ever boot returns 1.
// ESP8266: an append-only flash log (BootLog.h); ESP32: Preferences (NVS).
uint32_t bumpBootCounter();
}  // namespace habitat

struct HabitatConfig {
  const char* wifi_ssid;
  const char* wifi_pass;
  const char* mqtt_host;
  uint16_t mqtt_port;
  const char* mqtt_user;
  const char* mqtt_pass;
};

class HabitatNode {
 public:
  HabitatNode();

  bool beginWith(const char* node_id, const HabitatConfig& cfg);

#if defined(WIFI_SSID) && defined(WIFI_PASS) && defined(MQTT_HOST) && defined(MQTT_PORT) && \
    defined(MQTT_USER) && defined(MQTT_PASS)
  // Uses the macros from the sketch's secrets.h.
  bool begin(const char* node_id) {
    HabitatConfig cfg = {WIFI_SSID, WIFI_PASS, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS};
    return beginWith(node_id, cfg);
  }
#endif

  // Fixes seq now (first message is 1). Safe to call from another core on ESP32.
  void queue(uint8_t ind, float val, uint8_t dev, uint8_t q);
  // Call often: reconnects with backoff, drains the ring oldest first.
  void loop();
  uint32_t boot() const { return boot_; }

 private:
  void lock();
  void unlock();
  void connectWifi(uint32_t now);
  void connectMqtt(uint32_t now);
  void drain(uint32_t now);
  void diagnostics(uint32_t now);

  HabitatConfig cfg_;
  char node_[16];
  char topic_r_[40];
  char topic_status_[40];
  uint32_t boot_;
  uint32_t seq_;
  RingBuffer<habitat::PendingReading, 32> ring_;
  WiFiClient net_;
  MQTTClient mqtt_;
  bool wifi_was_up_;
  bool mqtt_was_up_;
  uint32_t wifi_retry_at_, wifi_backoff_ms_;
  uint32_t mqtt_retry_at_, mqtt_backoff_ms_;
  uint32_t last_diag_ms_;
  uint32_t last_dropped_;
#if defined(ARDUINO_ARCH_ESP32)
  SemaphoreHandle_t mutex_;
#endif
};
