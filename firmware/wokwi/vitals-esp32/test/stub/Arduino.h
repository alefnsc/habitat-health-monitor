// Host stand-in for Arduino.h, just enough for SparkFun's spo2_algorithm.cpp.
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#define PROGMEM
#ifdef __cplusplus
template <class T, class U> static inline T min(T a, U b) { return a < b ? a : (T)b; }
template <class T, class U> static inline T max(T a, U b) { return a > b ? a : (T)b; }
#endif
