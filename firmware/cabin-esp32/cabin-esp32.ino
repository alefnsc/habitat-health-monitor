// cabin-2 node: an ESP32 with a BMP280 barometer, published as ind "cabin_p" (hPa), dev BMP280.
// Educational prototype. Readings go to habitat/v1/r/cabin-2 through HabitatNode (Wi-Fi/MQTT).
//
// Board: ESP32 DevKit (esp32:esp32:esp32). BMP280 wiring: VCC on 3V3 (never 5V/VIN: the chip's limit
// is 3.6 V), GND, SDA on GPIO21, SCL on GPIO22, CSB and SDO open (I2C address 0x76).
// The driver is firmware/bmp280/bmp280_lite.h, copied next to this file by firmware/bmp280/sync.sh.
// The BMP280's own temperature is not published: cabin_temp stays with the DHT11 on cabin-1.
//
// secrets.h present -> readings are published over Wi-Fi/MQTT (copy secrets.example.h, fill it in).
// secrets.h missing -> serial-only mode: the pressure is printed as a "# bmp280 ..." line.
// A module that does not answer is reported once ("# bmp280 missing") and probed again later.

#if __has_include("secrets.h")
#include "secrets.h"
#include <HabitatNode.h>
#define CABIN2_MQTT 1
#else
#define CABIN2_MQTT 0
#endif

#include <Wire.h>
#include "bmp280_lite.h"

#if CABIN2_MQTT
static HabitatNode node;
#endif

static bmp280::Poller baro;

static void baroPoll(uint32_t now) {
  float p = 0;
  switch (baro.poll(now, 10000, &p)) {
    case bmp280::EV_READING:
#if CABIN2_MQTT
      node.queue(habitat::IND_CABIN_P, p, habitat::DEV_BMP280,
                 bmp280::inRange(p) ? 0 : habitat::Q_OUT_OF_RANGE);
#endif
      Serial.print(F("# bmp280 cabin_p hPa="));
      Serial.println(p, 2);
      break;
    case bmp280::EV_FOUND:
      Serial.print(F("# bmp280 found addr=0x"));
      Serial.println(baro.address(), HEX);
      break;
    case bmp280::EV_MISSING:
      Serial.println(F("# bmp280 missing at 0x76 and 0x77: no cabin_p"));
      break;
    case bmp280::EV_LOST:
      Serial.println(F("# bmp280 lost: no cabin_p until it answers again"));
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Wire.begin();  // ESP32 default pins: SDA GPIO21, SCL GPIO22
#if CABIN2_MQTT
  node.begin("cabin-2");
#else
  Serial.println(F("# cabin-2 serial-only mode (no secrets.h)"));
#endif
}

void loop() {
#if CABIN2_MQTT
  node.loop();
#endif
  baroPoll(millis());
  delay(5);
}
