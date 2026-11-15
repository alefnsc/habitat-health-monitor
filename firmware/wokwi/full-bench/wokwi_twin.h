// Wokwi twin only: stand-in part settings for firmware/exercise-uno (decision D40).
// The real sketch folder has no such file, so the bench build keeps its defaults (DHT11, active buzzer).
#define DHT_TYPE DHT22    // Wokwi has no DHT11 part; the DHT22 stands in for it
#define BUZZER_PASSIVE 1  // the Wokwi buzzer is a piezo played with tone()
