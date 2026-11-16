// Host tests for MqttLink.h (reconnect, backoff, failure lines, drain) against a fake port.
// Bench 2026-11-15: the hub Mac's DHCP address moved from .6 to .10. tilt-1 kept Wi-Fi, never
// reconnected, filled its ring and dropped 280 readings, printing only "# ring ... dropped=N".
#include <ArduinoJson.h>

#include <cassert>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "MqttLink.h"

using namespace habitat;

struct Pub {
  std::string topic, payload;
  bool retained;
  int qos;
};

struct FakePort {
  bool up = false;          // MQTT session state
  bool accept = true;       // next connect() succeeds
  std::string resolved;     // what resolve() answers; empty = DNS failure
  int rc = 0, err = 0;      // returnCode() / lastError() after a refused connect
  bool puback = true;       // publish() result
  int resolves = 0, connects = 0, polls = 0;
  std::vector<std::string> logs;
  std::vector<Pub> pubs;
  std::function<void()> on_publish;

  bool connected() { return up; }
  bool resolve(const char*, uint16_t, char* ip, size_t cap) {
    ++resolves;
    if (resolved.empty()) return false;
    snprintf(ip, cap, "%s", resolved.c_str());
    return true;
  }
  bool connect(const char*, const char*, const char*) {
    ++connects;
    up = accept;
    return accept;
  }
  int returnCode() { return rc; }
  int lastError() { return err; }
  bool publish(const char* topic, const char* payload, int len, bool retained, int qos) {
    if (on_publish) on_publish();
    if (!puback) return false;
    pubs.push_back({topic, std::string(payload, static_cast<size_t>(len)), retained, qos});
    return true;
  }
  void poll() { ++polls; }
  void lock() {}
  void unlock() {}
  void log(const char* line) { logs.push_back(line); }

  bool logged(const std::string& s) const {
    for (const auto& l : logs)
      if (l == s) return true;
    return false;
  }
  size_t readings() const {
    size_t n = 0;
    for (const auto& p : pubs) n += p.topic == "habitat/v1/r/tilt-1";
    return n;
  }
};

using Ring = RingBuffer<PendingReading, 32>;
using Link = MqttLink<FakePort, 32>;

static const char* kPass = "s3cret-pass";
static const char* kUser = "node-user";

static LinkConfig cfg(const char* host = "bench.local") {
  return LinkConfig{"tilt-1", 7, host, 1883, kUser, kPass, "habitat/v1/r/tilt-1",
                    "habitat/v1/status/tilt-1"};
}

static void push(Ring& ring, uint32_t seq) {
  ring.push(PendingReading{seq, 0, IND_TILT, static_cast<float>(seq % 2), DEV_KY017, 0});
}

static uint32_t seqOf(const Pub& p) {
  JsonDocument d;
  assert(!deserializeJson(d, p.payload));
  return d["seq"].as<uint32_t>();
}

int main() {
  {  // every refused connect prints rc, err, host and ip, never the secrets
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    port.accept = false;
    port.rc = 5;
    port.err = -10;
    link.begin(cfg(), 1000);
    link.loop(1000, true);
    assert(port.connects == 1);
    assert(port.logged("# mqtt fail rc=5 err=-10 host=bench.local ip=192.168.0.6 port=1883 retry_ms=1000"));
    for (const auto& l : port.logs) {
      assert(l.find(kPass) == std::string::npos);
      assert(l.find(kUser) == std::string::npos);
    }
  }
  {  // backoff doubles to 30 s, no attempt before it is due, one line per failure
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    port.accept = false;
    port.err = -3;  // LWMQTT_NETWORK_FAILED_CONNECT: nobody listens at that address
    link.begin(cfg(), 0);
    uint32_t at = 0;  // the first attempt is due at once
    const uint32_t want[] = {1000, 2000, 4000, 8000, 16000, 30000, 30000};
    for (uint32_t w : want) {
      int before = port.connects;
      link.loop(at, true);
      assert(port.connects == before + 1);
      char line[160];
      snprintf(line, sizeof line,
               "# mqtt fail rc=0 err=-3 host=bench.local ip=192.168.0.6 port=1883 retry_ms=%u",
               static_cast<unsigned>(w));
      assert(port.logs.back() == line);
      assert(link.backoff().retry_at == at + w);
      link.loop(at + w - 1, true);  // not due yet
      assert(port.connects == before + 1);
      at += w;
    }
    assert(port.logs.size() == 7);
  }
  {  // the incident: the hub moves from .6 to .10; re-resolving the name finds it again
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    link.begin(cfg(), 0);
    link.loop(0, true);
    assert(port.up && port.logged("# mqtt ok host=bench.local ip=192.168.0.6 port=1883"));
    assert(port.pubs.size() == 1 && port.pubs[0].topic == "habitat/v1/status/tilt-1");
    assert(port.pubs[0].payload == "online" && port.pubs[0].retained && port.pubs[0].qos == 1);

    port.up = false;  // broker gone from .6
    port.accept = false;
    port.err = -3;
    for (uint32_t s = 1; s <= 40; ++s) push(ring, s);  // readings keep coming
    link.loop(5000, true);
    assert(port.logged("# mqtt lost"));
    assert(port.logs.back() ==
           "# mqtt fail rc=0 err=-3 host=bench.local ip=192.168.0.6 port=1883 retry_ms=1000");
    assert(ring.size() == 32 && ring.dropped() == 8);

    port.resolved = "192.168.0.10";  // DHCP gave the hub a new address; mDNS answers with it
    port.accept = true;
    link.loop(6000, true);
    assert(port.resolves == 3);
    assert(port.logs[port.logs.size() - 1 - Link::kDrainPerLoop] ==
           "# mqtt ok host=bench.local ip=192.168.0.10 port=1883");
    assert(link.backoff().wait_ms == 1000);  // reset after a success
    // drains oldest first, kDrainPerLoop per pass: seq 9..12 now (1..8 were overwritten)
    assert(port.readings() == 4 && seqOf(port.pubs[2]) == 9 && seqOf(port.pubs[5]) == 12);
    for (int pass = 0; pass < 7; ++pass) link.loop(6001 + pass, true);
    assert(port.readings() == 32 && ring.size() == 0);
    assert(seqOf(port.pubs.back()) == 40);
    for (size_t i = 2; i < port.pubs.size(); ++i) {
      assert(seqOf(port.pubs[i]) == 7 + i);
      assert(!port.pubs[i].retained && port.pubs[i].qos == 1);
    }
  }
  {  // a name that does not resolve is a failure line too, with the same backoff
    FakePort port;
    Ring ring;
    Link link(port, ring);
    link.begin(cfg(), 0);
    link.loop(0, true);
    assert(port.connects == 0);
    assert(port.logged("# mqtt fail dns host=bench.local port=1883 retry_ms=1000"));
    link.loop(1000, true);
    assert(port.logs.back() == "# mqtt fail dns host=bench.local port=1883 retry_ms=2000");
  }
  {  // no Wi-Fi: no attempt and no line
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    link.begin(cfg(), 0);
    link.loop(0, false);
    assert(port.resolves == 0 && port.connects == 0 && port.logs.empty());
  }
  {  // a publish without PUBACK keeps the reading; the next pass sends it again
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    link.begin(cfg(), 0);
    link.loop(0, true);
    push(ring, 1);
    push(ring, 2);
    port.puback = false;
    link.loop(10, true);
    assert(ring.size() == 2 && port.readings() == 0);
    port.puback = true;
    link.loop(20, true);
    assert(ring.size() == 0 && port.readings() == 2);
    assert(seqOf(port.pubs[1]) == 1 && seqOf(port.pubs[2]) == 2);
    assert(port.polls == 3);
  }
  {  // an overflow during the publish (the sampling core on ESP32) must not pop a newer reading
    FakePort port;
    Ring ring;
    Link link(port, ring);
    port.resolved = "192.168.0.6";
    link.begin(cfg(), 0);
    link.loop(0, true);
    push(ring, 1);
    uint32_t next = 2;
    port.on_publish = [&] {
      if (next == 2)
        for (; next <= 33; ++next) push(ring, next);  // 1 is overwritten mid-publish
    };
    link.loop(10, true);
    // seq 1 went out once; 2 was not popped in its place, so 2..5 follow in order
    assert(seqOf(port.pubs[1]) == 1 && seqOf(port.pubs[2]) == 2);
    assert(ring.size() == 32 - 3);
  }
  puts("ok");
  return 0;
}
