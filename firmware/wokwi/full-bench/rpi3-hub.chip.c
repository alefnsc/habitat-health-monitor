// Raspberry Pi 3 Model B hub for the full bench circuit (decision D40): a drawing only.
// Wokwi has no Raspberry Pi 3 (it runs Linux), so this chip shows the hub's connections:
// USB_A to the UNO (USB serial 250000), PWR_IN (micro-USB 5 V 2.5 A), MICROSD, and the 40-pin header,
// which stays EMPTY. The hub software (Mosquitto, hub, console) runs on the real Pi. It drives nothing here.
#include "wokwi-api.h"

void chip_init(void) {}
