// Raspberry Pi 3 Model B hub for the full bench circuit (decision D40), as a circuit abstraction.
// Wokwi has no Raspberry Pi 3 (it runs Linux), so this chip stands in for the hub's job on the UNO link only:
// - RX/TX/GND are wired to the UNO's UART (D1/D0). On the bench this is the USB cable: the UNO's USB bridge feeds the
//   same UART, at 250000 baud (/dev/ttyACM0 on the Pi).
// - It reads the UNO's contract-v1 lines and judges each cabin reading against the NASA-STD-3001 cabin bands, worst
//   of the health box (outside it: "outside the limit") and the performance zone (outside it: "watch"), copied from
//   data/thresholds.json (a pytest checks they match). A flagged reading is not judged, as in the hub.
// - The "alert" control stands in for a space-weather (DONKI) act: it sends the same alarm command the hub's
//   actuator sends, so the UNO acks and the buzzer sounds. A cabin breach does not sound the buzzer, as on the hub.
// Mosquitto, the console, storage and the Mars link run on the real Pi; nothing here stores data. The 40-pin header,
// power and microSD pins are drawn only and stay unwired. Educational prototype, not a medical device.
#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Cabin bands from data/thresholds.json (NASA-STD-3001 Vol 2 Rev F, [V2 6012] health box, [V2 6013] performance).
#define TEMP_HEALTH_MIN 18
#define TEMP_HEALTH_MAX 27
#define TEMP_PERF_MIN 20
#define TEMP_PERF_MAX 25
#define RH_HEALTH_MIN 25
#define RH_HEALTH_MAX 75
#define RH_PERF_MIN 30
#define RH_PERF_MAX 60

#define HUB_BAUD 250000
#define HUB_LINE_MAX 256
#define HUB_TICK_US 200000

typedef enum { ST_OK = 0, ST_WATCH = 1, ST_ACT = 2, ST_UNKNOWN = 3 } hub_status_t;

typedef struct {
  uart_dev_t uart;
  uint32_t alert_attr;
  int alert_sent;            // -1 = nothing sent yet, else the last alarm state sent
  char line[HUB_LINE_MAX];
  uint32_t len;
  int overflow;
  char tx[48];
  int tx_busy;
  uint32_t readings, acks, banners, rejects;
  char last_log[200];
} hub_chip_t;

static void hub_log(hub_chip_t *c, const char *msg) {
  snprintf(c->last_log, sizeof c->last_log, "hub: %s", msg);
  printf("%s\n", c->last_log);
}

static int in_band(double v, double lo, double hi) { return v >= lo && v <= hi; }

static hub_status_t worst(hub_status_t a, hub_status_t b) { return a > b ? a : b; }

static hub_status_t cabin_status(const char *ind, double v) {
  if (strcmp(ind, "cabin_temp") == 0)
    return worst(in_band(v, TEMP_HEALTH_MIN, TEMP_HEALTH_MAX) ? ST_OK : ST_ACT,
                 in_band(v, TEMP_PERF_MIN, TEMP_PERF_MAX) ? ST_OK : ST_WATCH);
  if (strcmp(ind, "cabin_rh") == 0)
    return worst(in_band(v, RH_HEALTH_MIN, RH_HEALTH_MAX) ? ST_OK : ST_ACT,
                 in_band(v, RH_PERF_MIN, RH_PERF_MAX) ? ST_OK : ST_WATCH);
  return ST_UNKNOWN;
}

// The console's own key words.
static const char *status_words(hub_status_t s) {
  switch (s) {
    case ST_OK: return "within the limit (NASA-STD-3001)";
    case ST_WATCH: return "watch (NASA-STD-3001)";
    case ST_ACT: return "outside the limit (NASA-STD-3001)";
    default: return "not judged";
  }
}

// Substring scanning, like the firmware's own command parser: no JSON library in a chip.
static int str_field(const char *line, const char *key, char *out, size_t cap) {
  char pat[24];
  snprintf(pat, sizeof pat, "\"%s\":\"", key);
  const char *p = strstr(line, pat);
  if (!p) return 0;
  p += strlen(pat);
  size_t n = 0;
  while (p[n] && p[n] != '"' && n + 1 < cap) { out[n] = p[n]; n++; }
  out[n] = 0;
  return p[n] == '"';
}

static int num_field(const char *line, const char *key, double *out) {
  char pat[24];
  snprintf(pat, sizeof pat, "\"%s\":", key);
  const char *p = strstr(line, pat);
  if (!p) return 0;
  char *end;
  *out = strtod(p + strlen(pat), &end);
  return end != p + strlen(pat);
}

static void hub_handle_line(hub_chip_t *c, const char *line) {
  char msg[180], node[24], ind[24], unit[12], cmd[16], valtxt[16];
  if (line[0] == 0) return;
  if (line[0] == '#') {
    c->banners++;
    snprintf(msg, sizeof msg, "banner \"%.120s\"", line);
    hub_log(c, msg);
    return;
  }
  if (strncmp(line, "{\"v\":1,", 7) != 0) {
    c->rejects++;
    hub_log(c, "rejected a line that is not contract v1");
    return;
  }
  char type[12];
  if (str_field(line, "type", type, sizeof type) && strcmp(type, "ack") == 0 && str_field(line, "cmd", cmd, sizeof cmd)) {
    c->acks++;
    snprintf(msg, sizeof msg, "ack %s %s", cmd, strstr(line, "\"ok\":true") ? "ok" : "refused");
    hub_log(c, msg);
    return;
  }
  double val;
  const char *v = strstr(line, "\"val\":");
  if (!str_field(line, "node", node, sizeof node) || !str_field(line, "ind", ind, sizeof ind) ||
      !str_field(line, "unit", unit, sizeof unit) || !num_field(line, "val", &val) || !v) {
    c->rejects++;
    hub_log(c, "rejected a contract-v1 line with missing fields");
    return;
  }
  // Echo the value as the UNO wrote it (no float reformatting).
  size_t n = 0;
  for (v += 6; v[n] && v[n] != ',' && n + 1 < sizeof valtxt; n++) valtxt[n] = v[n];
  valtxt[n] = 0;
  c->readings++;
  hub_status_t s = strstr(line, "\"q\":[\"ok\"]") ? cabin_status(ind, val) : ST_UNKNOWN;
  snprintf(msg, sizeof msg, "%s %s %s %s -> %s", node, ind, valtxt, unit, status_words(s));
  hub_log(c, msg);
}

static void on_rx(void *user_data, uint8_t byte) {
  hub_chip_t *c = (hub_chip_t *)user_data;
  if (byte == '\r') return;
  if (byte == '\n') {
    c->line[c->len] = 0;
    if (c->overflow) {
      c->rejects++;
      hub_log(c, "rejected an over-long line");
    } else {
      hub_handle_line(c, c->line);
    }
    c->len = 0;
    c->overflow = 0;
    return;
  }
  if (c->len + 1 < HUB_LINE_MAX) c->line[c->len++] = (char)byte;
  else c->overflow = 1;
}

static void on_write_done(void *user_data) { ((hub_chip_t *)user_data)->tx_busy = 0; }

// Polls the alert control; on a change, sends the alarm command once, as the hub's DONKI actuator does.
static void on_tick(void *user_data) {
  hub_chip_t *c = (hub_chip_t *)user_data;
  int alert = attr_read(c->alert_attr) ? 1 : 0;
  if (alert == c->alert_sent || c->tx_busy) return;
  int n = snprintf(c->tx, sizeof c->tx, "{\"v\":1,\"cmd\":\"alarm\",\"on\":%s}\n", alert ? "true" : "false");
  c->tx_busy = 1;
  c->alert_sent = alert;
  hub_log(c, alert ? "space-weather alert: sending alarm on (as the hub's DONKI actuator)" : "alert cleared: sending alarm off");
  uart_write(c->uart, (uint8_t *)c->tx, (uint32_t)n);
}

void chip_init(void) {
  hub_chip_t *c = calloc(1, sizeof(hub_chip_t));
  c->alert_sent = 0;  // the UNO boots with the alarm off
  const uart_config_t uart = {
    .user_data = c,
    .rx = pin_init("RX", INPUT),
    .tx = pin_init("TX", INPUT_PULLUP),
    .baud_rate = HUB_BAUD,
    .rx_data = on_rx,
    .write_done = on_write_done,
  };
  c->uart = uart_init(&uart);
  c->alert_attr = attr_init("alert", 0);
  const timer_config_t timer = { .user_data = c, .callback = on_tick };
  timer_start(timer_init(&timer), HUB_TICK_US, true);
  printf("hub: Raspberry Pi 3 hub (circuit abstraction) listening to the UNO at 250000 baud\n");
}
