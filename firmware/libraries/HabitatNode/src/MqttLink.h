// The MQTT half of HabitatNode::loop(): reconnect with backoff, then drain the ring oldest first.
// Header-only, no Arduino includes: the board reaches MQTT, DNS and Serial through a Port, so the
// host tests (test/test_link.cpp) drive the same code with a fake.
//
// Port needs: bool connected(); bool resolve(host, port, ip_out, cap) (an IP literal or a hostname,
// e.g. a .local name over mDNS; it also points the client at that address); bool connect(id, user,
// pass); int returnCode(); int lastError(); bool publish(topic, payload, len, retained, qos);
// void poll(); void lock(); void unlock(); void log(line).
//
// Every failed attempt prints one line, never the user name or the password:
//   # mqtt fail rc=5 err=-10 host=bench.local ip=192.168.0.10 port=1883 retry_ms=2000
//   # mqtt fail dns host=bench.local port=1883 retry_ms=4000
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "ReadingFormat.h"
#include "RingBuffer.h"

namespace habitat {

// Doubling retry delay: start, 2x, 4x ... capped at max. Wrap-safe on millis().
struct Backoff {
  uint32_t start_ms;
  uint32_t max_ms;
  uint32_t wait_ms;
  uint32_t retry_at;
  explicit Backoff(uint32_t start = 1000, uint32_t max = 30000)
      : start_ms(start), max_ms(max), wait_ms(start), retry_at(0) {}
  bool due(uint32_t now) const { return static_cast<int32_t>(now - retry_at) >= 0; }
  // After a failed try at `now`: schedules the next one and returns how long it waits.
  uint32_t failed(uint32_t now) {
    uint32_t w = wait_ms;
    retry_at = now + w;
    wait_ms = w * 2 > max_ms ? max_ms : w * 2;
    return w;
  }
  void succeeded() { wait_ms = start_ms; }
};

struct LinkConfig {
  const char* node;  // also the MQTT client id
  uint32_t boot;
  const char* host;  // IP or hostname, re-resolved on every attempt (a DHCP change is picked up)
  uint16_t port;
  const char* user;
  const char* pass;
  const char* topic_r;
  const char* topic_status;
};

template <class Port, size_t N>
class MqttLink {
 public:
  static const uint8_t kDrainPerLoop = 4;

  MqttLink(Port& port, RingBuffer<PendingReading, N>& ring) : port_(port), ring_(ring) {}

  void begin(const LinkConfig& cfg, uint32_t now) {
    cfg_ = cfg;
    backoff_ = Backoff();
    backoff_.retry_at = now;
    was_up_ = false;
  }

  // One pass. Reconnects only while Wi-Fi is up and the backoff is due; drains while connected.
  void loop(uint32_t now, bool wifi_up) {
    if (!port_.connected()) {
      if (was_up_) {
        was_up_ = false;
        port_.log("# mqtt lost");
      }
      if (!wifi_up || !backoff_.due(now) || !connect(now)) return;
    }
    was_up_ = true;
    port_.poll();
    drain(now);
  }

  const Backoff& backoff() const { return backoff_; }

 private:
  bool connect(uint32_t now) {
    char line[160];
    char ip[40];
    if (!port_.resolve(cfg_.host, cfg_.port, ip, sizeof ip)) {
      uint32_t w = backoff_.failed(now);
      snprintf(line, sizeof line, "# mqtt fail dns host=%s port=%u retry_ms=%lu", cfg_.host,
               static_cast<unsigned>(cfg_.port), static_cast<unsigned long>(w));
      port_.log(line);
      return false;
    }
    if (!port_.connect(cfg_.node, cfg_.user, cfg_.pass)) {
      uint32_t w = backoff_.failed(now);
      snprintf(line, sizeof line, "# mqtt fail rc=%d err=%d host=%s ip=%s port=%u retry_ms=%lu",
               port_.returnCode(), port_.lastError(), cfg_.host, ip,
               static_cast<unsigned>(cfg_.port), static_cast<unsigned long>(w));
      port_.log(line);
      return false;
    }
    snprintf(line, sizeof line, "# mqtt ok host=%s ip=%s port=%u", cfg_.host, ip,
             static_cast<unsigned>(cfg_.port));
    port_.log(line);
    port_.publish(cfg_.topic_status, "online", 6, true, 1);
    backoff_.succeeded();
    return true;
  }

  void drain(uint32_t now) {
    char buf[256];
    char line[96];
    for (uint8_t n = 0; n < kDrainPerLoop && port_.connected(); ++n) {
      PendingReading r;
      port_.lock();
      bool have = ring_.peekOldest(r);
      port_.unlock();
      if (!have) return;
      size_t len = formatReading(r, cfg_.node, cfg_.boot, now, buf, sizeof buf);
      if (len == 0) {  // cannot happen with legal values; drop rather than block the ring
        port_.lock();
        ring_.popOldest();
        port_.unlock();
        continue;
      }
      // QoS 1: publish() returns true only after the PUBACK arrived.
      if (!port_.publish(cfg_.topic_r, buf, static_cast<int>(len), false, 1)) return;
      port_.lock();
      PendingReading oldest;
      // Pop only if the entry we sent is still the oldest (an overflow may have dropped it).
      if (ring_.peekOldest(oldest) && oldest.seq == r.seq) ring_.popOldest();
      port_.unlock();
      snprintf(line, sizeof line, "# pub %s %.3f seq=%lu age_ms=%lu", kIndNames[r.ind],
               static_cast<double>(r.val), static_cast<unsigned long>(r.seq),
               static_cast<unsigned long>(now - r.sampled_ms));
      port_.log(line);
    }
  }

  Port& port_;
  RingBuffer<PendingReading, N>& ring_;
  LinkConfig cfg_ = {};
  Backoff backoff_;
  bool was_up_ = false;
};

}  // namespace habitat
