// Host tests for the pure block of vitals-esp32.ino (extracted by run_host_tests.sh).
#include <ArduinoJson.h>

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#include "pure_block.h"

int main() {
  char buf[256];
  {  // serial-only line is valid contract-v1 JSON
    size_t n = fmtLine(buf, sizeof buf, 1, 7, 0, VI_HR, 72.0f, "MAX30102", QF_SETTLING | QF_MOTION);
    assert(n > 0 && n == strlen(buf) && n <= 256);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d.size() == 11 && d["v"] == 1 && d["seq"] == 7 && d["boot"] == 1 && d["age_ms"] == 0);
    assert(std::string(d["node"].as<const char*>()) == "vitals-1");
    assert(std::string(d["ind"].as<const char*>()) == "hr" && std::string(d["unit"].as<const char*>()) == "bpm");
    assert(std::string(d["src"].as<const char*>()) == "hobby" && std::string(d["dev"].as<const char*>()) == "MAX30102");
    assert(d["q"].size() == 2 && std::string(d["q"][0].as<const char*>()) == "motion" &&
           std::string(d["q"][1].as<const char*>()) == "settling");
    assert(d["val"] == 72);
    fmtLine(buf, sizeof buf, 1, 8, 0, VI_SKIN_TEMP, 33.456f, "MLX90614", 0);
    assert(strstr(buf, "\"val\":33.46,") && strstr(buf, "\"q\":[\"ok\"]"));
    fmtLine(buf, sizeof buf, 1, 9, 0, VI_MOTION, 0.12345f, "MPU6050", 0);
    assert(strstr(buf, "\"val\":0.123,") && strstr(buf, "\"unit\":\"g\""));
    assert(fmtLine(buf, 30, 1, 1, 0, VI_HR, 1, "MAX30102", 0) == 0);
    assert(fmtLine(buf, sizeof buf, 1, 1, 0, VI_HR, NAN, "MAX30102", 0) == 0);
    assert(fmtLine(buf, sizeof buf, 1, 1, 0, 9, 1, "MAX30102", 0) == 0);
  }
  {  // contact and settling: first 4 s after contact are settling, no finger is no_contact
    ContactTracker c = {};
    assert(!c.block(10000) && vitalFlags(c, false) == QF_NO_CONTACT && vitalFlags(c, true) == QF_NO_CONTACT);
    for (int i = 0; i < 4; i++) {
      assert(c.block(90000));
      assert(vitalFlags(c, false) == QF_SETTLING);
    }
    assert(c.block(90000) && vitalFlags(c, false) == 0);
    assert(vitalFlags(c, true) == QF_MOTION);
    assert(!c.block(49999) && c.since == 0);
    assert(c.block(50000) && c.settling());  // settling again after the finger returns
  }
  {  // MLX90614 CRC and decoding. 0x3AF7 counts = 0.02 K each = 25.0 C is not exact, so compute it.
    uint16_t raw = (uint16_t)lroundf((36.6f + 273.15f) / 0.02f);
    uint8_t lsb = raw & 0xFF, msb = raw >> 8;
    uint8_t pkt[5] = {0xB4, 0x07, 0xB5, lsb, msb};  // 0x5A write, command, 0x5A read, data
    uint8_t pec = smbusCrc8(pkt, 5);
    float c = 0;
    assert(mlxDecode(0x5A, 0x07, lsb, msb, pec, true, &c) && fabsf(c - 36.6f) < 0.02f);
    assert(!mlxDecode(0x5A, 0x07, lsb, msb, (uint8_t)(pec ^ 1), true, &c));  // bad PEC
    assert(mlxDecode(0x5A, 0x07, lsb, msb, (uint8_t)(pec ^ 1), false, &c));   // PEC check off
    assert(!mlxDecode(0x5A, 0x07, lsb, 0x80 | msb, pec, false, &c));          // error flag
    assert(smbusCrc8((const uint8_t*)"123456789", 9) == 0xF4);                // CRC-8 (poly 0x07) check value
    uint8_t zero[1] = {0};
    assert(smbusCrc8(zero, 1) == 0);
  }
  {  // skin flags: room air is no_contact; settling for 30 s then ok when steady
    SkinFlags f = {};
    for (int i = 0; i < 15; i++) assert(f.update(24.0f) == (QF_SETTLING | QF_NO_CONTACT));
    assert(f.update(24.0f) == QF_NO_CONTACT);
    SkinFlags g = {};
    for (int i = 0; i < 15; i++) g.update(34.0f);
    assert(g.update(34.05f) == 0);
    assert(g.update(34.6f) == QF_SETTLING);  // moved > 0.1 C against 30 s earlier
    SkinFlags h = {};
    assert((h.update(400.0f) & QF_OUT_OF_RANGE) && (h.update(-80.0f) & QF_OUT_OF_RANGE));
  }
  {  // motion RMS: still at 1 g gives about 0; a 0.2 g offset gives 0.2; one value per 50 samples
    MotionRms m = {};
    float rms = -1;
    for (int i = 0; i < 49; i++) assert(!m.push(0, 0, 16384, &rms));
    assert(m.push(0, 0, 16384, &rms) && rms < 1e-6f);
    for (int i = 0; i < 49; i++) assert(!m.push(0, 0, (int16_t)(16384 * 1.2), &rms));
    assert(m.push(0, 0, (int16_t)(16384 * 1.2), &rms) && fabsf(rms - 0.2f) < 0.001f);
    // |a| matters, not the axis: tilted at rest is still still
    for (int i = 0; i < 49; i++) m.push(16384, 0, 0, &rms);
    assert(m.push(16384, 0, 0, &rms) && rms < 1e-6f);
  }
  {  // gate: stays on for four 1 s values after the last shake
    MotionGate g = {};
    assert(!g.active());
    g.push(0.08f, 0.05f);
    for (int i = 0; i < 3; i++) {
      assert(g.active());
      g.push(0.01f, 0.05f);
    }
    assert(g.active());
    g.push(0.01f, 0.05f);
    assert(!g.active());
    g.push(0.05f, 0.05f);  // equal is not above
    assert(!g.active());
  }
  puts("ok");
  return 0;
}
