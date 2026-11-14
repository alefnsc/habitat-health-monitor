"""python -m hub.sim --file <path> [--speed F] [--backdate] [--loop]"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from hub.config import load_settings
from hub.sim import TOPIC_STATUS, load_replay, next_boot, replay


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay a session as node sim-1.")
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--backdate", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--state", type=Path, default=Path(".state/sim-1.boot"))
    a = ap.parse_args()

    import paho.mqtt.client as mqtt

    cfg = load_settings(os.environ)

    lines = load_replay(a.file)
    boot = next_boot(a.state)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-1-{boot}")
    if cfg.mqtt_user:
        client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
    client.will_set(TOPIC_STATUS, b"offline", qos=1, retain=True)
    client.connect(cfg.mqtt_host, cfg.mqtt_port)
    client.loop_start()
    client.publish(TOPIC_STATUS, b"online", qos=1, retain=True).wait_for_publish()

    def publish(topic: str, payload: bytes) -> None:
        client.publish(topic, payload, qos=1).wait_for_publish()

    try:
        n = replay(
            lines, publish, time.sleep, boot=boot, speed=a.speed, backdate=a.backdate,
            loop=a.loop,
        )  # fmt: skip
        print(f"published {n} messages as sim-1 boot {boot}")
    finally:
        client.publish(TOPIC_STATUS, b"offline", qos=1, retain=True).wait_for_publish()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
