// Reading message formatter (contract section 4.1). Arduino-independent;
// depends only on ArduinoJson.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace habitat {

// Indicator table index (section 4.3). Order matches kIndNames/kIndUnits.
enum Ind : uint8_t {
  IND_HR, IND_SPO2, IND_SKIN_TEMP, IND_BODY_TEMP, IND_BP_SYS, IND_BP_DIA,
  IND_GLUCOSE, IND_SLEEP_H, IND_MOOD, IND_SYMPTOM, IND_CABIN_TEMP,
  IND_CABIN_RH, IND_CABIN_P, IND_CABIN_CO2, IND_CABIN_LUX, IND_MOTION,
  IND_LOAD_RAW, IND_COUNT
};

// Device table index (section 4.1 dev list, plus MPU6050, and the D35 hobby modules NTC and KY039).
enum Dev : uint8_t {
  DEV_MAX30102, DEV_DS18B20, DEV_MLX90614, DEV_SCD41, DEV_BME280, DEV_DHT22,
  DEV_DHT11, DEV_BH1750, DEV_HX711, DEV_H10, DEV_MANUAL, DEV_CAMERA,
  DEV_MPU6050, DEV_NTC, DEV_KY039, DEV_COUNT
};

// Quality flag bits (section 4.4, node-raised ones). Bit order is output order.
enum QBits : uint8_t {
  Q_MOTION = 1 << 0,
  Q_NO_CONTACT = 1 << 1,
  Q_SETTLING = 1 << 2,
  Q_LEADS_OFF = 1 << 3,
  Q_OUT_OF_RANGE = 1 << 4,
};

struct PendingReading {
  uint32_t seq;
  uint32_t sampled_ms;  // node millis() at sampling
  uint8_t ind;          // Ind
  float val;
  uint8_t dev;          // Dev
  uint8_t q;            // QBits
};

extern const char* const kIndNames[IND_COUNT];
extern const char* const kIndUnits[IND_COUNT];
extern const char* const kDevNames[DEV_COUNT];

// Writes one NUL-terminated JSON reading into out. Returns bytes written
// (excluding the NUL), or 0 if it would not fit in cap or an index is invalid.
// age_ms = now_ms - sampled_ms in unsigned 32-bit arithmetic.
size_t formatReading(const PendingReading& r, const char* node, uint32_t boot,
                     uint32_t now_ms, char* out, size_t cap);

}  // namespace habitat
