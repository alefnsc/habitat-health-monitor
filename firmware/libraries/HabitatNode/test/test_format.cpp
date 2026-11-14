#include <ArduinoJson.h>

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#include "ReadingFormat.h"

using namespace habitat;

static PendingReading base() {
  return PendingReading{7, 10000, IND_CABIN_TEMP, 24.3f, DEV_DHT22, 0};
}

int main() {
  char buf[256];
  {  // test_format_fields
    size_t n = formatReading(base(), "cabin-1", 3, 10250, buf, sizeof buf);
    assert(n > 0 && n == std::strlen(buf));
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d["v"] == 1);
    assert(std::string(d["node"].as<const char*>()) == "cabin-1");
    assert(d["boot"] == 3 && d["seq"] == 7 && d["age_ms"] == 250);
    assert(std::string(d["ind"].as<const char*>()) == "cabin_temp");
    assert(std::fabs(d["val"].as<double>() - 24.3) < 1e-4);
    assert(std::string(d["unit"].as<const char*>()) == "C");
    assert(std::string(d["src"].as<const char*>()) == "hobby");
    assert(std::string(d["dev"].as<const char*>()) == "DHT22");
    assert(d["q"].size() == 1 && std::string(d["q"][0].as<const char*>()) == "ok");
    assert(d["crew"].isNull());
    assert(d.size() == 11);
  }
  {  // test_format_flags
    PendingReading r = base();
    r.q = Q_NO_CONTACT | Q_MOTION;
    formatReading(r, "cabin-1", 3, 10250, buf, sizeof buf);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d["q"].size() == 2);
    assert(std::string(d["q"][0].as<const char*>()) == "motion");
    assert(std::string(d["q"][1].as<const char*>()) == "no_contact");
    assert(!std::strstr(buf, "\"ok\""));
  }
  {  // test_format_age_after_wrap
    PendingReading r = base();
    r.sampled_ms = 4294967000u;
    formatReading(r, "cabin-1", 3, 704, buf, sizeof buf);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d["age_ms"] == 1000);
  }
  {  // test_format_size_limit
    PendingReading r{4294967295u, 0, IND_CABIN_CO2, 40000.0f, DEV_MAX30102,
                     Q_MOTION | Q_NO_CONTACT | Q_SETTLING | Q_LEADS_OFF | Q_OUT_OF_RANGE};
    size_t n = formatReading(r, "exercise-1", 4294967295u, 4294967295u, buf, 256);
    assert(n > 0 && n <= 256);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d["q"].size() == 5);
  }
  {  // test_format_cap_too_small
    char small[40];
    assert(formatReading(base(), "cabin-1", 3, 10250, small, sizeof small) == 0);
  }
  {  // test_format_decimals
    PendingReading r = base();
    r.val = 24.299999f;
    formatReading(r, "cabin-1", 3, 10250, buf, sizeof buf);
    assert(std::strstr(buf, "\"val\":24.3,"));
    assert(!std::strstr(buf, "24.29"));
    r.ind = IND_SPO2; r.val = 97.0f; r.dev = DEV_MAX30102;
    formatReading(r, "vitals-1", 3, 10250, buf, sizeof buf);
    assert(std::strstr(buf, "\"val\":97,"));
    r.ind = IND_SKIN_TEMP; r.val = 33.456f;
    formatReading(r, "vitals-1", 3, 10250, buf, sizeof buf);
    assert(std::strstr(buf, "\"val\":33.46,"));
    r.ind = IND_MOTION; r.val = 0.12345f;
    formatReading(r, "vitals-1", 3, 10250, buf, sizeof buf);
    assert(std::strstr(buf, "\"val\":0.123,"));
  }
  std::puts("ok");
  return 0;
}
