#include "HabitatNode.h"

#if defined(ARDUINO_ARCH_ESP32)
#include <Preferences.h>
#else
#include "BootLog.h"
extern "C" uint32_t _EEPROM_start;  // the core's EEPROM sector; nothing else on these nodes uses it
#endif

namespace habitat {

#if !defined(ARDUINO_ARCH_ESP32)
namespace {
// The EEPROM sector of the flash layout, driven as raw NOR flash (BootLog.h says why).
struct Esp8266Sector {
  uint32_t base = reinterpret_cast<uint32_t>(&_EEPROM_start) - 0x40200000u;
  bool read(uint32_t off, void* buf, uint32_t len) {
    return ESP.flashRead(base + off, static_cast<uint32_t*>(buf), len);
  }
  bool program(uint32_t off, const void* buf, uint32_t len) {
    return ESP.flashWrite(base + off, static_cast<const uint32_t*>(buf), len);
  }
  bool erase() { return ESP.flashEraseSector(base / BootLog::kSectorBytes); }
};
}  // namespace
#endif

uint32_t bumpBootCounter() {
  uint32_t n = 0;
#if defined(ARDUINO_ARCH_ESP32)
  Preferences prefs;  // NVS is journaled: a power loss keeps the old value, never blanks it
  prefs.begin("habitat", false);
  n = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", n);
  prefs.end();
#else
  Esp8266Sector sector;
  n = BootLog::bump(sector);  // one 8-byte program per boot; no erase until the sector is full
#endif
  return n;
}

}  // namespace habitat

namespace {
const uint32_t kDiagEveryMs = 10000;
const uint32_t kDnsTimeoutMs = 2000;  // ESP8266 only; bounds the loop stall on a missing .local name

bool due(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }
}  // namespace

HabitatNode::HabitatNode()
    : boot_(0), seq_(0),
      mqtt_(512),
      port_{*this},
      link_(port_, ring_),
      wifi_was_up_(false),
      last_diag_ms_(0), last_dropped_(0) {
  node_[0] = topic_r_[0] = topic_status_[0] = '\0';
#if defined(ARDUINO_ARCH_ESP32)
  mutex_ = xSemaphoreCreateMutex();
#endif
}

void HabitatNode::lock() {
#if defined(ARDUINO_ARCH_ESP32)
  xSemaphoreTake(mutex_, portMAX_DELAY);
#endif
}

void HabitatNode::unlock() {
#if defined(ARDUINO_ARCH_ESP32)
  xSemaphoreGive(mutex_);
#endif
}

bool HabitatNode::beginWith(const char* node_id, const HabitatConfig& cfg) {
  cfg_ = cfg;
  strncpy(node_, node_id, sizeof node_ - 1);
  node_[sizeof node_ - 1] = '\0';
  snprintf(topic_r_, sizeof topic_r_, "habitat/v1/r/%s", node_);
  snprintf(topic_status_, sizeof topic_status_, "habitat/v1/status/%s", node_);
  boot_ = habitat::bumpBootCounter();
  Serial.printf("# %s boot=%lu\n", node_, static_cast<unsigned long>(boot_));

  WiFi.mode(WIFI_STA);
  mqtt_.begin(net_);  // the address is set before each attempt (Port::resolve)
  mqtt_.setKeepAlive(10);
  mqtt_.setCleanSession(true);
  mqtt_.setTimeout(2000);
  mqtt_.setWill(topic_status_, "offline", true, 1);
  uint32_t now = millis();
  wifi_backoff_.retry_at = now;
  link_.begin({node_, boot_, cfg_.mqtt_host, cfg_.mqtt_port, cfg_.mqtt_user, cfg_.mqtt_pass,
               topic_r_, topic_status_},
              now);
  last_diag_ms_ = now;
  return true;
}

void HabitatNode::queue(uint8_t ind, float val, uint8_t dev, uint8_t q) {
  habitat::PendingReading r;
  r.sampled_ms = millis();
  r.ind = ind;
  r.val = val;
  r.dev = dev;
  r.q = q;
  lock();
  r.seq = ++seq_;
  ring_.push(r);
  unlock();
}

void HabitatNode::connectWifi(uint32_t now) {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifi_was_up_) {
      wifi_was_up_ = true;
      wifi_backoff_.succeeded();
      Serial.printf("# wifi ok ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(),
                    static_cast<int>(WiFi.RSSI()));
    }
    return;
  }
  wifi_was_up_ = false;
  if (!wifi_backoff_.due(now)) return;
  WiFi.disconnect();
  WiFi.begin(cfg_.wifi_ssid, cfg_.wifi_pass);  // returns at once; status is polled
  wifi_backoff_.failed(now);
}

bool HabitatNode::Port::connected() { return node.mqtt_.connected(); }

bool HabitatNode::Port::resolve(const char* host, uint16_t port, char* ip, size_t cap) {
  IPAddress addr;
  if (!addr.fromString(host)) {
#if defined(ARDUINO_ARCH_ESP32)
    if (!WiFi.hostByName(host, addr)) return false;
#else
    // lwIP in the ESP8266 core is built with LWIP_DNS_SUPPORT_MDNS_QUERIES: a .local name works.
    if (!WiFi.hostByName(host, addr, kDnsTimeoutMs)) return false;
#endif
  }
  node.mqtt_.setHost(addr, port);
  snprintf(ip, cap, "%s", addr.toString().c_str());
  return true;
}

bool HabitatNode::Port::connect(const char* id, const char* user, const char* pass) {
  return node.mqtt_.connect(id, user, pass);
}

int HabitatNode::Port::returnCode() { return static_cast<int>(node.mqtt_.returnCode()); }

int HabitatNode::Port::lastError() { return static_cast<int>(node.mqtt_.lastError()); }

bool HabitatNode::Port::publish(const char* topic, const char* payload, int len, bool retained,
                                int qos) {
  return node.mqtt_.publish(topic, payload, len, retained, qos);
}

void HabitatNode::Port::poll() { node.mqtt_.loop(); }

void HabitatNode::Port::log(const char* line) { Serial.println(line); }

void HabitatNode::diagnostics(uint32_t now) {
  lock();
  size_t size = ring_.size();
  uint32_t dropped = ring_.dropped();
  unlock();
  if (dropped != last_dropped_) {
    last_dropped_ = dropped;
    Serial.printf("# ring dropped=%lu\n", static_cast<unsigned long>(dropped));
  }
  if (due(now, last_diag_ms_ + kDiagEveryMs)) {
    last_diag_ms_ = now;
    Serial.printf("# ring size=%lu dropped=%lu\n", static_cast<unsigned long>(size),
                  static_cast<unsigned long>(dropped));
  }
}

void HabitatNode::loop() {
  uint32_t now = millis();
  connectWifi(now);
  link_.loop(now, WiFi.status() == WL_CONNECTED);
  diagnostics(now);
}
