// Host tests for the pure block of tilt-esp8266.ino (extracted by run_host_tests.sh).
#include <cassert>
#include <cstdio>
#include <cstring>

#include "pure_block.h"

int main() {
  {  // the first sample sets the level without a change
    Debouncer d;
    assert(!d.feed(0, 1000) && d.stable == 0);
  }
  {  // a bounce burst shorter than 30 ms collapses into one change
    Debouncer d;
    d.feed(0, 0);
    assert(!d.feed(1, 100));
    assert(!d.feed(0, 105));
    assert(!d.feed(1, 110));
    assert(!d.feed(1, 125));                  // held 15 ms
    assert(d.feed(1, 140) && d.stable == 1);  // held 30 ms
    assert(!d.feed(1, 200));
  }
  {  // a glitch that returns before 30 ms is ignored
    Debouncer d;
    d.feed(0, 0);
    assert(!d.feed(1, 50));
    assert(!d.feed(0, 60));
    assert(!d.feed(0, 200) && d.stable == 0);
  }
  {  // heartbeat every 10 s, also across the millis() wrap
    assert(!heartbeatDue(0, 9999) && heartbeatDue(0, 10000));
    assert(heartbeatDue(4294967000u, 9800u));
  }
  {  // the serial-only line is contract-v1 shaped
    char buf[256];
    size_t n = fmtTiltLine(buf, sizeof buf, 1, 7, 1);
    assert(n > 0 && n == strlen(buf));
    assert(strstr(buf, "\"node\":\"tilt-1\"") && strstr(buf, "\"ind\":\"tilt\"") &&
           strstr(buf, "\"val\":1,") && strstr(buf, "\"unit\":\"state\"") &&
           strstr(buf, "\"dev\":\"KY017\"") && strstr(buf, "\"seq\":7,") &&
           strstr(buf, "\"q\":[\"ok\"]"));
    assert(fmtTiltLine(buf, 20, 1, 1, 0) == 0);
  }
  std::puts("ok");
  return 0;
}
