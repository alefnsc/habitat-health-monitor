"""Command path to the rig and MQTT nodes (H14, D7)."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hub.contract import ContractError, _decode

if TYPE_CHECKING:
    from hub.mqtt import MqttPublisher
    from hub.serial_rig import RigLink

log = logging.getLogger("hub.commands")

CMDS = ("servo", "alarm", "cal", "tare")
RIG_NODE = "exercise-1"
SERIAL_NODES: frozenset[str] = frozenset({RIG_NODE, "cabin-1"})  # D40: one UNO, one USB link


@dataclass(frozen=True)
class Command:
    v: int
    cmd: Literal["servo", "alarm", "cal", "tare"]
    angle_deg: int | None = None
    on: bool | None = None
    mass_kg: float | None = None


def parse_command(raw: bytes | str | dict) -> Command:
    msg = _decode(raw, None if isinstance(raw, dict) else 256)
    v = msg.get("v")
    if isinstance(v, bool) or v != 1 or not isinstance(v, int):
        raise ContractError("bad_version")
    cmd = msg.get("cmd")
    if cmd not in CMDS:
        raise ContractError("bad_value:cmd")
    if cmd == "servo":
        if "angle_deg" not in msg:
            raise ContractError("missing_field:angle_deg")
        a = msg["angle_deg"]
        if isinstance(a, bool) or not isinstance(a, int):
            raise ContractError("bad_type:angle_deg")
        if not 0 <= a <= 180:
            raise ContractError("bad_value:angle_deg")
        return Command(1, "servo", angle_deg=a)
    if cmd == "alarm":
        if "on" not in msg:
            raise ContractError("missing_field:on")
        if not isinstance(msg["on"], bool):
            raise ContractError("bad_type:on")
        return Command(1, "alarm", on=msg["on"])
    if cmd == "cal":
        if "mass_kg" not in msg:
            raise ContractError("missing_field:mass_kg")
        m = msg["mass_kg"]
        if isinstance(m, bool) or not isinstance(m, int | float):
            raise ContractError("bad_type:mass_kg")
        if not m > 0:
            raise ContractError("bad_value:mass_kg")
        return Command(1, "cal", mass_kg=float(m))
    return Command(1, "tare")


def encode_command(c: Command) -> bytes:
    d: dict = {"v": c.v, "cmd": c.cmd}
    if c.cmd == "servo":
        d["angle_deg"] = c.angle_deg
    elif c.cmd == "alarm":
        d["on"] = c.on
    elif c.cmd == "cal":
        d["mass_kg"] = c.mass_kg
    return json.dumps(d, separators=(",", ":")).encode("utf-8") + b"\n"


def command_topic(node: str) -> str:
    """MQTT topic for a command to `node`. The hub bridges only the rig's topic to the serial link."""
    return f"habitat/v1/cmd/{RIG_NODE if node in SERIAL_NODES else node}"


class CommandRouter:
    def __init__(self, rig: RigLink | None, publisher: MqttPublisher | None) -> None:
        self.rig, self.publisher = rig, publisher

    def send(self, node: str, cmd: Command) -> None:
        try:
            if node in SERIAL_NODES:
                if self.rig is None:
                    log.warning("no rig link, dropped %s for %s", cmd.cmd, node)
                    return
                self.rig.send(cmd)
                return
            if self.publisher is None:
                log.warning("no mqtt publisher, dropped %s for %s", cmd.cmd, node)
                return
            retain = cmd.cmd in ("servo", "alarm")
            self.publisher.publish(
                command_topic(node), encode_command(cmd).strip(), qos=1, retain=retain
            )
        except Exception:
            log.exception("command %s to %s failed", cmd.cmd, node)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish one command to a node over MQTT.")
    ap.add_argument("--node", default=RIG_NODE)
    ap.add_argument("--cmd", required=True, choices=CMDS)
    ap.add_argument("--angle-deg", type=int)
    ap.add_argument("--on", choices=("true", "false"))
    ap.add_argument("--mass-kg", type=float)
    a = ap.parse_args()
    d = {"v": 1, "cmd": a.cmd, "angle_deg": a.angle_deg, "mass_kg": a.mass_kg,
         "on": None if a.on is None else a.on == "true"}  # fmt: skip
    cmd = parse_command({k: v for k, v in d.items() if v is not None})

    import paho.mqtt.client as mqtt

    from hub.config import load_settings

    cfg = load_settings(os.environ)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt_user:
        client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
    client.connect(cfg.mqtt_host, cfg.mqtt_port)
    client.loop_start()
    retain = cmd.cmd in ("servo", "alarm")
    client.publish(
        command_topic(a.node), encode_command(cmd).strip(), qos=1, retain=retain
    ).wait_for_publish()
    client.loop_stop()
    client.disconnect()
    print(f"sent {cmd.cmd} to {a.node}")


if __name__ == "__main__":
    main()
