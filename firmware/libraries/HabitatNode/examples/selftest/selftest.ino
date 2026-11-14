// Bench sketch: one flagged motion reading every 2 s. The reading carries the
// settling flag, so it is never assessed even if a hub is running.
// Copy the matching secrets.example.h to secrets.h in this folder first.
#include "secrets.h"
#include <HabitatNode.h>

#if defined(ARDUINO_ARCH_ESP32)
static const char* kNodeId = "vitals-1";
#else
static const char* kNodeId = "cabin-1";
#endif

HabitatNode node;
static uint32_t lastQueued = 0;

void setup() {
  Serial.begin(115200);
  node.begin(kNodeId);
}

void loop() {
  node.loop();
  if (millis() - lastQueued >= 2000) {
    lastQueued = millis();
    node.queue(habitat::IND_MOTION, 0.0f, habitat::DEV_MPU6050, habitat::Q_SETTLING);
  }
}
