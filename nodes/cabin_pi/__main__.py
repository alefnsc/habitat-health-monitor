"""python -m nodes.cabin_pi: run the cabin node.

Environment (same names as the hub's .env where they overlap):
  HUB_MQTT_HOST, HUB_MQTT_PORT, HUB_MQTT_USER, HUB_MQTT_PASS   broker (host empty = print only)
  CABIN_I2C_BUS (default 1), CABIN_DHT_GPIO (BCM pin, empty = no DHT22), CABIN_STATE_DIR (var)
Options: --stdout prints the lines instead of publishing (bench check, no broker needed).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from .bme280 import Bme280, BmeError
from .node import NODE, Cabin, Ring, format_reading, next_boot
from .scd41 import Scd41

log = logging.getLogger("cabin")


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nodes.cabin_pi")
    ap.add_argument("--stdout", action="store_true", help="print lines, do not publish")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    from .bus import SmbusI2C

    bus = SmbusI2C(int(os.environ.get("CABIN_I2C_BUS", "1")))
    try:
        bme: Bme280 | None = Bme280.probe(bus)
        _say(f"# bme280 at 0x{bme.addr:02X}")
    except BmeError as e:
        _say(f"# {e}")
        bme = None
    scd = Scd41(bus)
    dht = None
    if os.environ.get("CABIN_DHT_GPIO"):
        from .dht22 import gpio_reader

        dht = gpio_reader(int(os.environ["CABIN_DHT_GPIO"]))
        _say("# dht22 on" if dht else "# dht22 requested but adafruit_dht is not installed")

    boot = next_boot(os.environ.get("CABIN_STATE_DIR", "var"))
    _say(f"# {NODE} boot={boot}")
    cabin = Cabin(bme, scd, dht, log=_say)
    ring, seq = Ring(), 0

    client = None
    host = os.environ.get("HUB_MQTT_HOST", "")
    if host and not args.stdout:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{NODE}-{boot}")
        client.username_pw_set(
            os.environ.get("HUB_MQTT_USER", ""), os.environ.get("HUB_MQTT_PASS", "")
        )
        client.will_set(f"habitat/v1/status/{NODE}", "offline", qos=1, retain=True)
        client.on_connect = lambda c, *_: c.publish(f"habitat/v1/status/{NODE}", "online", 1, True)
        client.reconnect_delay_set(1, 30)
        client.connect_async(host, int(os.environ.get("HUB_MQTT_PORT", "1883")), keepalive=10)
        client.loop_start()

    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    cabin.start(time.monotonic())
    while not stop:
        now = time.monotonic()
        for s in cabin.step(now):
            ring.push(s)
        while ring.q and (client is None or client.is_connected()):
            s = ring.q[0]
            seq += 1
            line = format_reading(s, boot, seq, time.monotonic())
            if client is None:
                print(line, flush=True)
            elif client.publish(f"habitat/v1/r/{NODE}", line, qos=1).rc != 0:
                seq -= 1
                break
            ring.q.popleft()
        if ring.dropped:
            _say(f"# ring dropped={ring.dropped}")
            ring.dropped = 0
        time.sleep(1.0)
    if client:
        client.publish(f"habitat/v1/status/{NODE}", "offline", 1, True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
