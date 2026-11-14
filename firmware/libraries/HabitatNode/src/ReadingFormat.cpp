#include "ReadingFormat.h"

#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>

namespace habitat {

const char* const kIndNames[IND_COUNT] = {
    "hr", "spo2", "skin_temp", "body_temp", "bp_sys", "bp_dia", "glucose",
    "sleep_h", "mood", "symptom", "cabin_temp", "cabin_rh", "cabin_p",
    "cabin_co2", "cabin_lux", "motion", "load_raw", "tilt"};
const char* const kIndUnits[IND_COUNT] = {
    "bpm", "%", "C", "C", "mmHg", "mmHg", "mg/dL", "h", "1-5", "code", "C",
    "%", "hPa", "ppm", "lx", "g", "N", "state"};
const char* const kDevNames[DEV_COUNT] = {
    "MAX30102", "DS18B20", "MLX90614", "SCD41", "BME280", "DHT22", "DHT11",
    "BH1750", "HX711", "H10", "manual", "camera", "MPU6050", "NTC", "KY039", "KY017", "RING"};

// Decimals per indicator; unlisted indicators use 1.
static const uint8_t kDecimals[IND_COUNT] = {
    /*hr*/ 0, /*spo2*/ 0, /*skin_temp*/ 2, /*body_temp*/ 1, /*bp_sys*/ 0,
    /*bp_dia*/ 0, /*glucose*/ 0, /*sleep_h*/ 1, /*mood*/ 0, /*symptom*/ 0,
    /*cabin_temp*/ 1, /*cabin_rh*/ 1, /*cabin_p*/ 1, /*cabin_co2*/ 0,
    /*cabin_lux*/ 0, /*motion*/ 3, /*load_raw*/ 1, /*tilt*/ 0};

static const char* const kFlagNames[5] = {"motion", "no_contact", "settling",
                                          "leads_off", "out_of_range"};

size_t formatReading(const PendingReading& r, const char* node, uint32_t boot,
                     uint32_t now_ms, char* out, size_t cap) {
  if (out == nullptr || cap == 0 || r.ind >= IND_COUNT || r.dev >= DEV_COUNT)
    return 0;

  // Fixed decimals as raw JSON text: avoids float artifacts such as 24.29999924.
  char num[24];
  double v = static_cast<double>(r.val);
  if (!isfinite(v)) v = 0;
  snprintf(num, sizeof num, "%.*f", kDecimals[r.ind], v);

  JsonDocument doc;
  doc["v"] = 1;
  doc["node"] = node;
  doc["boot"] = boot;
  doc["seq"] = r.seq;
  doc["age_ms"] = static_cast<uint32_t>(now_ms - r.sampled_ms);
  doc["ind"] = kIndNames[r.ind];
  doc["val"] = serialized(static_cast<const char*>(num));
  doc["unit"] = kIndUnits[r.ind];
  doc["src"] = "hobby";
  doc["dev"] = kDevNames[r.dev];
  JsonArray q = doc["q"].to<JsonArray>();
  if ((r.q & 0x1F) == 0) {
    q.add("ok");
  } else {
    for (uint8_t i = 0; i < 5; ++i)
      if (r.q & (1u << i)) q.add(kFlagNames[i]);
  }

  size_t need = measureJson(doc);
  if (need == 0 || need >= cap) return 0;
  return serializeJson(doc, out, cap);
}

}  // namespace habitat
