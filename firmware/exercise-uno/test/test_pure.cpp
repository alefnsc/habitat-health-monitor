// Host tests for the pure block of exercise-uno.ino (extracted by run_host_tests.sh).
#include <ArduinoJson.h>

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>

#define CELL_CAPACITY_KG 50
#include "pure_block.h"

static std::string str(JsonDocument& d, const char* k) { return d[k].as<const char*>(); }

int main() {
  char buf[256];
  {  // value formatting: two decimals, trailing zeros trimmed, never a float printf
    char o[24];
    fmtVal(o, sizeof o, 98.1f); assert(!strcmp(o, "98.1"));
    fmtVal(o, sizeof o, 97.0f); assert(!strcmp(o, "97"));
    fmtVal(o, sizeof o, -0.004f); assert(!strcmp(o, "0"));
    fmtVal(o, sizeof o, -12.345f); assert(!strcmp(o, "-12.35") || !strcmp(o, "-12.34"));
    fmtVal(o, sizeof o, NAN); assert(!strcmp(o, "0"));
    fmtVal(o, sizeof o, 1e30f); assert(!strcmp(o, "10000000"));
    assert(fmtVal(o, 3, 1234.5f) == 0);
  }
  {  // reading line is valid contract-v1 JSON with the expected fields
    size_t n = buildReading(buf, sizeof buf, "exercise-1", 3, 41, "load_raw", 98.1f, "N", "HX711", QF_SETTLING);
    assert(n == strlen(buf));
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d.size() == 11);
    assert(d["v"] == 1 && d["boot"] == 3 && d["seq"] == 41 && d["age_ms"] == 0);
    assert(str(d, "node") == "exercise-1" && str(d, "ind") == "load_raw" && str(d, "unit") == "N");
    assert(str(d, "src") == "hobby" && str(d, "dev") == "HX711");
    assert(fabs(d["val"].as<double>() - 98.1) < 1e-4);
    assert(d["q"].size() == 1 && std::string(d["q"][0].as<const char*>()) == "settling");
    assert(!d["type"].is<const char*>());
  }
  {  // clean reading carries ["ok"]; several flags keep contract order
    buildReading(buf, sizeof buf, "exercise-1", 1, 1, "hr", 72, "bpm", "KY039", 0);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(d["q"].size() == 1 && std::string(d["q"][0].as<const char*>()) == "ok");
    buildReading(buf, sizeof buf, "exercise-1", 1, 1, "load_raw", 1, "N", "HX711", QF_SETTLING | QF_OUT_OF_RANGE);
    JsonDocument e;
    assert(!deserializeJson(e, buf));
    assert(e["q"].size() == 2 && std::string(e["q"][0].as<const char*>()) == "settling" &&
           std::string(e["q"][1].as<const char*>()) == "out_of_range");
  }
  {  // bench_line_budget: boot 999, seq 7 digits (35 h at 80 SPS), |val| < 1000 N and one flag
     // stay within 160 bytes; absurd counters and three flags stay within the 256-byte contract limit
    size_t n = buildReading(buf, sizeof buf, "exercise-1", 999, 9999999, "load_raw", -999.99f, "N", "HX711",
                            QF_OUT_OF_RANGE);
    assert(n > 0 && n <= 160);
    n = buildReading(buf, sizeof buf, "exercise-1", 999, 9999999, "load_raw", -999.99f, "N", "HX711",
                     QF_SETTLING | QF_OUT_OF_RANGE);
    assert(n > 0 && n <= 175);  // both flags together are rare (a calibrated cell, first 2 s, overloaded)
    n = buildReading(buf, sizeof buf, "exercise-1", 4294967295u, 4294967295u, "load_raw", -9999999.0f, "N",
                     "HX711", QF_SETTLING | QF_OUT_OF_RANGE | QF_NO_CONTACT);
    assert(n > 0 && n <= 256);
    assert(buildReading(buf, 40, "exercise-1", 1, 1, "load_raw", 1, "N", "HX711", 0) == 0);  // too small
  }
  {  // acks
    buildAck(buf, sizeof buf, "servo", true, NULL);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(str(d, "type") == "ack" && str(d, "cmd") == "servo" && d["ok"] == true && d["v"] == 1);
    assert(str(d, "node") == "exercise-1" && d["err"].isNull());
    buildAck(buf, sizeof buf, "foo", false, "unknown");
    JsonDocument e;
    assert(!deserializeJson(e, buf));
    assert(e["ok"] == false && str(e, "err") == "unknown" && str(e, "cmd") == "foo");
  }
  {  // command parsing (D7)
    Cmd c;
    assert(parseCommand("{\"v\":1,\"cmd\":\"servo\",\"angle_deg\":150}", &c));
    assert(!strcmp(c.name, "servo") && c.hasAngle && c.angle == 150 && !c.hasOn && !c.hasMass);
    assert(parseCommand("{\"v\":1,\"cmd\":\"servo\",\"angle_deg\":200}", &c) && c.angle == 200);
    assert(parseCommand("{ \"v\": 1, \"cmd\": \"alarm\", \"on\": true }", &c) && c.hasOn && c.on);
    assert(parseCommand("{\"v\":1,\"cmd\":\"alarm\",\"on\":false}", &c) && c.hasOn && !c.on);
    assert(parseCommand("{\"v\":1,\"cmd\":\"cal\",\"mass_kg\":2.00}", &c) && c.hasMass &&
           fabs(c.mass - 2.0f) < 1e-6);
    assert(parseCommand("{\"v\":1,\"cmd\":\"cal\",\"mass_kg\":10}", &c) && fabs(c.mass - 10.0f) < 1e-6);
    assert(parseCommand("{\"v\":1,\"cmd\":\"tare\"}", &c) && !strcmp(c.name, "tare") && !c.hasMass);
    assert(parseCommand("{\"v\":1,\"cmd\":\"foo\"}", &c) && !strcmp(c.name, "foo"));
    assert(!parseCommand("{\"v\":1}", &c));
    assert(!parseCommand("{\"cmd\":\"\"}", &c));
    // the echoed name must stay safe inside the ack JSON
    assert(parseCommand("{\"cmd\":\"a\\\\b-c\"}", &c));
    for (const char* p = c.name; *p; p++) assert(isalnum((unsigned char)*p) || *p == '_');
    // long names are cut, not overrun
    assert(parseCommand("{\"cmd\":\"abcdefghijklmnopqrstuvwxyz\"}", &c) && strlen(c.name) == 13);
  }
  {  // two-mass calibration (bench_cal_two_points arithmetic)
    float k; long c0;
    const float k_true = 4000.0f; const long c0_true = 85000;
    float fa = 2.00f * kGravity, fb = 10.00f * kGravity;
    long ca = c0_true + lroundf(k_true * fa), cb = c0_true + lroundf(k_true * fb);
    assert(calSolve(ca, fa, cb, fb, &k, &c0));
    assert(fabs(k - k_true) < 1.0f && labs(c0 - c0_true) < 3);
    assert(fabs(calValue(cb, k, c0) - 98.1f) < 0.05f);
    long cc = c0_true + lroundf(k_true * 5.00f * kGravity);
    assert(fabs(calValue(cc, k, c0) - 49.05f) < 0.05f * 49.05f * 0.02f + 0.01f);
    assert(!calSolve(ca, fa, cb, fa + 0.05f, &k, &c0));  // same mass
    assert(!calSolve(ca, fa, ca, fb, &k, &c0));          // no span
    // a reversed-wired cell still calibrates (negative slope)
    assert(calSolve(c0_true - lroundf(k_true * fa), fa, c0_true - lroundf(k_true * fb), fb, &k, &c0) &&
           k < 0);
  }
  {  // flags (bench_uncalibrated, bench_settling_after_boot, bench_out_of_range)
    assert(loadFlags(false, 50000, 100000, 100.0f) == QF_SETTLING);
    assert(loadFlags(false, 50000, 8000000, 8000.0f) == QF_SETTLING);  // no range check uncalibrated
    assert(loadFlags(true, 1999, 0, 0.0f) == QF_SETTLING);
    assert(loadFlags(true, 2000, 0, 0.0f) == 0);
    assert(loadFlags(true, 5000, 0, 98.1f) == 0);
    assert(loadFlags(true, 5000, 0, 490.6f) == QF_OUT_OF_RANGE);   // 50 kg x 9.81 = 490.5 N
    assert(loadFlags(true, 5000, 0, -490.6f) == QF_OUT_OF_RANGE);
    assert(loadFlags(true, 5000, 8388607L, 1.0f) == QF_OUT_OF_RANGE);
  }
  {  // NTC conversion: the Wokwi / common-module formula, 10 k at 25 C is mid-scale
    float c;
    assert(ntcCelsius(511.5f, &c) && fabs(c - 25.0f) < 0.05f);
    assert(ntcCelsius(1023.0f * 0.4f, &c) && c > 25.0f);   // lower NTC share = warmer
    assert(ntcCelsius(1023.0f * 0.6f, &c) && c < 25.0f);
    assert(!ntcCelsius(2.0f, &c) && !ntcCelsius(1020.0f, &c));
    assert(!ntcCelsius(NAN, &c));
  }
  {  // NTC settling: 6 samples (30 s) first, then a 0.1 C change over 30 s
    Settle30 s; memset(&s, 0, sizeof s);
    for (int i = 0; i < 6; i++) assert(s.update(33.0f));
    assert(!s.update(33.05f));
    assert(s.update(33.5f));  // moved more than 0.1 C against the sample 30 s earlier
  }
  {  // pulse estimate: 72 bpm sine on a DC offset, sampled every 10 ms
    HrEst h; h.reset();
    uint32_t t = 1000;
    for (int i = 0; i < 6000; i++, t += 10)
      h.push((uint16_t)(512 + 40.0 * sin(2 * M_PI * (1.2) * (i * 0.01))), t);
    assert(h.hasContact() && !h.settling());
    assert(fabs(h.bpm() - 72.0f) < 2.0f);
  }
  {  // no finger: flat signal with a little noise is no_contact and has no estimate
    HrEst h; h.reset();
    uint32_t t = 1000;
    for (int i = 0; i < 3000; i++, t += 10) h.push((uint16_t)(700 + (i % 3) - 1), t);
    assert(!h.hasContact() && h.bpm() == 0.0f);
  }
  {  // contact lost after good beats clears the estimate
    HrEst h; h.reset();
    uint32_t t = 1000;
    for (int i = 0; i < 3000; i++, t += 10)
      h.push((uint16_t)(512 + 40.0 * sin(2 * M_PI * 1.0 * (i * 0.01))), t);
    assert(h.hasContact());
    for (int i = 0; i < 400; i++, t += 10) h.push(512, t);
    assert(!h.hasContact() && h.bpm() == 0.0f);
  }
  {  // irregular beats stay "settling"
    HrEst h; h.reset();
    uint32_t t = 1000; double ph = 0;
    for (int i = 0; i < 6000; i++, t += 10) {
      double f = (i / 100) % 2 ? 0.8 : 1.8;  // alternating rate
      ph += 2 * M_PI * f * 0.01;
      h.push((uint16_t)(512 + 40.0 * sin(ph)), t);
    }
    assert(h.settling());
  }
  {  // node per line: the DHT11 lines say cabin-1 (D40)
    buildReading(buf, sizeof buf, "cabin-1", 2, 7, "cabin_temp", 23.5f, "C", "DHT11", 0);
    JsonDocument d;
    assert(!deserializeJson(d, buf));
    assert(str(d, "node") == "cabin-1" && str(d, "ind") == "cabin_temp" && str(d, "dev") == "DHT11");
    assert(fabs(d["val"].as<double>() - 23.5) < 1e-4);
    size_t n = buildReading(buf, sizeof buf, "cabin-1", 999, 9999999, "cabin_rh", 100.0f, "%", "DHT11",
                            QF_OUT_OF_RANGE);
    assert(n > 0 && n <= 160);
  }
  {  // DHT11 range flags (datasheet ranges 0..50 C and 20..90 %RH); NaN is out of range
    assert(rangeFlag(23.0f, 0, 50) == 0 && rangeFlag(0.0f, 0, 50) == 0 && rangeFlag(50.0f, 0, 50) == 0);
    assert(rangeFlag(-1.0f, 0, 50) == QF_OUT_OF_RANGE && rangeFlag(51.0f, 0, 50) == QF_OUT_OF_RANGE);
    assert(rangeFlag(95.0f, 20, 90) == QF_OUT_OF_RANGE && rangeFlag(NAN, 0, 50) == QF_OUT_OF_RANGE);
  }
  {  // three failed reads in a row before no_contact; a good read resets the count
    FailCount f; memset(&f, 0, sizeof f);
    assert(!f.fail() && !f.fail() && f.fail() && f.fail());
    f.ok();
    assert(!f.fail());
  }
  puts("ok");
  return 0;
}
