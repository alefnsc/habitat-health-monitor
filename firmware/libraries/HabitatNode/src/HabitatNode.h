// Node runtime shared by the ESP sketches: boot counter, sequence numbers, a
// 32-entry ring of unsent readings, and an MQTT link with a retained last will.
// ESP8266 and ESP32 only. Include the sketch's secrets.h BEFORE this header if
// you want the one-argument begin(node_id); otherwise call beginWith().
#pragma once

#include <Arduino.h>
#include <MQTT.h>

#include "MqttLink.h"
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
  const char* mqtt_host;  // an IP or a hostname (.local works over mDNS); resolved on each try
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
  // Call often: reconnects with backoff, drains the ring oldest first. Every failed MQTT attempt
  // prints "# mqtt fail ..." with the host and the address it resolved to (MqttLink.h).
  void loop();
  uint32_t boot() const { return boot_; }

 private:
  void lock();
  void unlock();
  void connectWifi(uint32_t now);
  void diagnostics(uint32_t now);

  // What MqttLink needs from the board: the MQTT client, DNS, Serial and the ring lock.
  struct Port {
    HabitatNode& node;
    bool connected();
    bool resolve(const char* host, uint16_t port, char* ip, size_t cap);
    bool connect(const char* id, const char* user, const char* pass);
    int returnCode();
    int lastError();
    bool publish(const char* topic, const char* payload, int len, bool retained, int qos);
    void poll();
    void lock() { node.lock(); }
    void unlock() { node.unlock(); }
    void log(const char* line);
  };

  HabitatConfig cfg_;
  char node_[16];
  char topic_r_[40];
  char topic_status_[40];
  uint32_t boot_;
  uint32_t seq_;
  RingBuffer<habitat::PendingReading, 32> ring_;
  WiFiClient net_;
  MQTTClient mqtt_;
  Port port_;
  habitat::MqttLink<Port, 32> link_;
  bool wifi_was_up_;
  habitat::Backoff wifi_backoff_;
  uint32_t last_diag_ms_;
  uint32_t last_dropped_;
#if defined(ARDUINO_ARCH_ESP32)
  SemaphoreHandle_t mutex_;
#endif
};
