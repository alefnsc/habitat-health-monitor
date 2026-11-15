// Native tests for the Raspberry Pi hub chip (rpi3-hub.chip.c) against a host stand-in for wokwi-api.h.
// The chip source is included directly so the tests can read its state. This does NOT prove the chip builds or
// runs on wokwi.com; that is checked by hand in the saved project.
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../rpi3-hub.chip.c"

// ---- host runtime: captures what the chip registers and what it writes ----
static uart_config_t g_uart;
static timer_config_t g_timer;
static uint32_t g_timer_us;
static uint32_t g_baud;
static uint32_t g_alert;          // the chip's "alert" control
static char g_tx[256];            // bytes the chip wrote to the UNO
static uint32_t g_tx_len;

pin_t pin_init(const char *name, uint32_t mode) { (void)name; (void)mode; return 1; }
uart_dev_t uart_init(const uart_config_t *c) { g_uart = *c; g_baud = c->baud_rate; return 1; }
bool uart_write(uart_dev_t u, uint8_t *buf, uint32_t n) {
  (void)u;
  memcpy(g_tx + g_tx_len, buf, n);
  g_tx_len += n;
  g_tx[g_tx_len] = 0;
  if (g_uart.write_done) g_uart.write_done(g_uart.user_data);
  return true;
}
timer_t timer_init(const timer_config_t *c) { g_timer = *c; return 1; }
void timer_start(timer_t t, uint32_t us, bool repeat) { (void)t; (void)repeat; g_timer_us = us; }
uint32_t attr_init(const char *name, uint32_t d) { assert(strcmp(name, "alert") == 0); g_alert = d; return 7; }
uint32_t attr_read(uint32_t id) { assert(id == 7); return g_alert; }

static hub_chip_t *chip(void) { return (hub_chip_t *)g_uart.user_data; }
static void feed(const char *s) { for (; *s; s++) g_uart.rx_data(g_uart.user_data, (uint8_t)*s); }
static void tick(void) { g_timer.callback(g_timer.user_data); }
static void tx_clear(void) { g_tx_len = 0; g_tx[0] = 0; }

#define READING(ind, val, unit, q) \
  "{\"v\":1,\"node\":\"cabin-1\",\"boot\":3,\"seq\":9,\"age_ms\":0,\"ind\":\"" ind "\",\"val\":" val \
  ",\"unit\":\"" unit "\",\"src\":\"hobby\",\"dev\":\"DHT11\",\"q\":[" q "]}\r\n"

static void expect_log(const char *needle) {
  if (!strstr(chip()->last_log, needle)) {
    printf("expected \"%s\" in \"%s\"\n", needle, chip()->last_log);
    assert(0);
  }
}

int main(void) {
  chip_init();
  assert(g_baud == 250000);   // the UNO's USB serial rate (exercise-uno Serial.begin)
  assert(g_timer_us == 200000);

  // A cabin reading is counted and judged against the NASA-STD-3001 bands, worst of health and performance.
  feed(READING("cabin_temp", "24.0", "C", "\"ok\""));
  assert(chip()->readings == 1);
  expect_log("cabin-1 cabin_temp 24.0 C");
  expect_log("within the limit");
  feed(READING("cabin_temp", "26.0", "C", "\"ok\""));  expect_log("watch");
  feed(READING("cabin_temp", "28.3", "C", "\"ok\""));  expect_log("outside the limit");
  feed(READING("cabin_temp", "27.0", "C", "\"ok\""));  expect_log("watch");             // 27 is inside the health box
  feed(READING("cabin_temp", "17.9", "C", "\"ok\""));  expect_log("outside the limit");
  feed(READING("cabin_rh", "52", "%", "\"ok\""));      expect_log("within the limit");
  feed(READING("cabin_rh", "65", "%", "\"ok\""));      expect_log("watch");
  feed(READING("cabin_rh", "80", "%", "\"ok\""));      expect_log("outside the limit");
  feed(READING("cabin_rh", "24", "%", "\"ok\""));      expect_log("outside the limit");
  assert(chip()->readings == 9);

  // A flagged reading is stored but not judged, like the hub (a flagged reading is `unknown`).
  feed(READING("cabin_temp", "0", "C", "\"no_contact\""));
  expect_log("not judged");
  assert(chip()->readings == 10);

  // A reading with no rule here is counted but not judged.
  feed("{\"v\":1,\"node\":\"exercise-1\",\"boot\":3,\"seq\":10,\"age_ms\":0,\"ind\":\"load_raw\",\"val\":12,"
       "\"unit\":\"count\",\"src\":\"hobby\",\"dev\":\"HX711\",\"q\":[\"ok\"]}\n");
  expect_log("not judged");
  assert(chip()->readings == 11);

  // Banners and acks.
  feed("# exercise-1 boot=3\n");
  assert(chip()->banners == 1);
  feed("{\"v\":1,\"node\":\"exercise-1\",\"type\":\"ack\",\"cmd\":\"alarm\",\"ok\":true}\n");
  assert(chip()->acks == 1);
  expect_log("ack alarm ok");
  feed("{\"v\":1,\"node\":\"exercise-1\",\"type\":\"ack\",\"cmd\":\"servo\",\"ok\":false,\"err\":\"not_built\"}\n");
  assert(chip()->acks == 2);
  expect_log("ack servo refused");

  // Anything else is rejected, including an over-long line; the next good line still parses.
  feed("hello\n");
  assert(chip()->rejects == 1);
  char longline[400];
  memset(longline, 'x', sizeof longline - 2);
  longline[sizeof longline - 2] = '\n';
  longline[sizeof longline - 1] = 0;
  feed(longline);
  assert(chip()->rejects == 2);
  feed(READING("cabin_rh", "50", "%", "\"ok\""));
  assert(chip()->readings == 12);

  // Bytes may arrive split anywhere.
  const char *split = READING("cabin_temp", "22.5", "C", "\"ok\"");
  for (const char *p = split; *p; p++) { char one[2] = {*p, 0}; feed(one); }
  assert(chip()->readings == 13);
  expect_log("cabin_temp 22.5 C");

  // The space-weather alert control sends the same alarm command as the hub's DONKI actuator, once per change.
  tx_clear();
  tick();
  assert(g_tx_len == 0);
  g_alert = 1;
  tick();
  assert(strcmp(g_tx, "{\"v\":1,\"cmd\":\"alarm\",\"on\":true}\n") == 0);
  tx_clear();
  tick();
  assert(g_tx_len == 0);  // no repeat while the control stays on
  g_alert = 0;
  tick();
  assert(strcmp(g_tx, "{\"v\":1,\"cmd\":\"alarm\",\"on\":false}\n") == 0);

  // A cabin breach does not sound the buzzer: the real hub only sends alarm for a space-weather act.
  tx_clear();
  feed(READING("cabin_temp", "35.0", "C", "\"ok\""));
  tick();
  assert(g_tx_len == 0);

  printf("hub chip ok\n");
  return 0;
}
