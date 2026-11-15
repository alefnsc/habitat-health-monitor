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
const uint32_t kBackoffStartMs = 1000;
const uint32_t kBackoffMaxMs = 30000;
const uint32_t kDiagEveryMs = 10000;
const uint8_t kDrainPerLoop = 4;

uint32_t nextBackoff(uint32_t b) { return b * 2 > kBackoffMaxMs ? kBackoffMaxMs : b * 2; }
bool due(uint32_t now, uint32_t at) { return static_cast<int32_t>(now - at) >= 0; }
}  // namespace

HabitatNode::HabitatNode()
    : mqtt_(512),
      boot_(0), seq_(0), wifi_was_up_(false), mqtt_was_up_(false),
      wifi_retry_at_(0), wifi_backoff_ms_(kBackoffStartMs),
      mqtt_retry_at_(0), mqtt_backoff_ms_(kBackoffStartMs),
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
  mqtt_.begin(cfg_.mqtt_host, cfg_.mqtt_port, net_);
  mqtt_.setKeepAlive(10);
  mqtt_.setCleanSession(true);
  mqtt_.setTimeout(2000);
  mqtt_.setWill(topic_status_, "offline", true, 1);
  uint32_t now = millis();
  wifi_retry_at_ = mqtt_retry_at_ = now;
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
      wifi_backoff_ms_ = kBackoffStartMs;
      Serial.printf("# wifi ok ip=%s rssi=%d\n", WiFi.localIP().toString().c_str(),
                    static_cast<int>(WiFi.RSSI()));
    }
    return;
  }
  wifi_was_up_ = false;
  if (!due(now, wifi_retry_at_)) return;
  WiFi.disconnect();
  WiFi.begin(cfg_.wifi_ssid, cfg_.wifi_pass);  // returns at once; status is polled
  wifi_retry_at_ = now + wifi_backoff_ms_;
  wifi_backoff_ms_ = nextBackoff(wifi_backoff_ms_);
}

void HabitatNode::connectMqtt(uint32_t now) {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt_.connected()) {
    mqtt_was_up_ = true;
    return;
  }
  if (mqtt_was_up_) {
    mqtt_was_up_ = false;
    Serial.println("# mqtt lost");
  }
  if (!due(now, mqtt_retry_at_)) return;
  if (mqtt_.connect(node_, cfg_.mqtt_user, cfg_.mqtt_pass)) {
    Serial.println("# mqtt ok");
    mqtt_.publish(topic_status_, "online", true, 1);
    mqtt_was_up_ = true;
    mqtt_backoff_ms_ = kBackoffStartMs;
  } else {
    mqtt_retry_at_ = now + mqtt_backoff_ms_;
    mqtt_backoff_ms_ = nextBackoff(mqtt_backoff_ms_);
  }
}

void HabitatNode::drain(uint32_t now) {
  char buf[256];
  for (uint8_t n = 0; n < kDrainPerLoop && mqtt_.connected(); ++n) {
    habitat::PendingReading r;
    lock();
    bool have = ring_.peekOldest(r);
    unlock();
    if (!have) return;
    size_t len = habitat::formatReading(r, node_, boot_, now, buf, sizeof buf);
    if (len == 0) {  // cannot happen with legal values; drop rather than block the ring
      lock();
      ring_.popOldest();
      unlock();
      continue;
    }
    // QoS 1: publish() returns true only after the PUBACK arrived.
    if (!mqtt_.publish(topic_r_, buf, static_cast<int>(len), false, 1)) return;
    lock();
    habitat::PendingReading oldest;
    // Pop only if the entry we sent is still the oldest (an overflow may have dropped it).
    if (ring_.peekOldest(oldest) && oldest.seq == r.seq) ring_.popOldest();
    unlock();
    Serial.printf("# pub %s %.3f seq=%lu age_ms=%lu\n", habitat::kIndNames[r.ind],
                  static_cast<double>(r.val), static_cast<unsigned long>(r.seq),
                  static_cast<unsigned long>(now - r.sampled_ms));
  }
}

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
  connectMqtt(now);
  if (mqtt_.connected()) {
    mqtt_.loop();
    drain(now);
  }
  diagnostics(now);
}
