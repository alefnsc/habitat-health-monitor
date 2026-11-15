import logging
from dataclasses import replace

import pytest

import hub.serial_rig as sr
from hub.commands import Command, CommandRouter, command_topic, encode_command, parse_command
from hub.contract import ContractError
from hub.mqtt import route_message
from hub.serial_rig import RigLink


def test_encode_servo():
    assert (
        encode_command(Command(1, "servo", angle_deg=90))
        == b'{"v":1,"cmd":"servo","angle_deg":90}\n'
    )


def test_encode_others():
    assert encode_command(Command(1, "alarm", on=True)) == b'{"v":1,"cmd":"alarm","on":true}\n'
    assert encode_command(Command(1, "cal", mass_kg=2.0)) == b'{"v":1,"cmd":"cal","mass_kg":2.0}\n'
    assert encode_command(Command(1, "tare")) == b'{"v":1,"cmd":"tare"}\n'


@pytest.mark.parametrize(
    ("msg", "reason"),
    [
        ({"v": 1, "cmd": "servo", "angle_deg": 200}, "bad_value:angle_deg"),
        ({"v": 1, "cmd": "servo", "angle_deg": 45.5}, "bad_type:angle_deg"),
        ({"v": 1, "cmd": "dance"}, "bad_value:cmd"),
        ({"v": 1, "cmd": "alarm"}, "missing_field:on"),
        ({"v": 1, "cmd": "servo"}, "missing_field:angle_deg"),
        ({"v": 1, "cmd": "cal", "mass_kg": 0}, "bad_value:mass_kg"),
        ({"v": 2, "cmd": "tare"}, "bad_version"),
    ],
)
def test_reject(msg, reason):
    with pytest.raises(ContractError) as e:
        parse_command(msg)
    assert e.value.reason == reason


class FakePort:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    def close(self):
        pass


def rig(settings, ingestor=None):
    link = RigLink(replace(settings, serial_port="x"), ingestor)
    link._port = FakePort()
    return link


def test_rig_send_writes_once(settings):
    link = rig(settings)
    assert link.send(Command(1, "servo", angle_deg=45)) is True
    assert link._port.writes == [b'{"v":1,"cmd":"servo","angle_deg":45}\n']


def test_rig_send_disconnected(settings, caplog):
    link = RigLink(replace(settings, serial_port="x"), None)
    with caplog.at_level(logging.WARNING):
        assert link.send(Command(1, "tare")) is False
    assert "rig not connected" in caplog.text


def test_resend_on_reconnect(settings):
    link = rig(settings)
    link.send(Command(1, "servo", angle_deg=150))
    link.send(Command(1, "alarm", on=True))
    link.send(Command(1, "cal", mass_kg=2.0))
    new = FakePort()
    link.resend_state(new)
    assert new.writes == [
        b'{"v":1,"cmd":"servo","angle_deg":150}\n',
        b'{"v":1,"cmd":"alarm","on":true}\n',
    ]
    assert sr  # module imported for monkeypatch symmetry


class Pub:
    def __init__(self):
        self.calls = []

    def publish(self, topic, payload, *, qos=1, retain=False):
        self.calls.append((topic, payload, qos, retain))


def test_router(settings):
    link, pub = rig(settings), Pub()
    r = CommandRouter(link, pub)
    assert r.send("exercise-1", Command(1, "alarm", on=True)) is None
    assert link._port.writes and pub.calls == []
    r.send("vitals-1", Command(1, "alarm", on=True))  # an MQTT node
    assert pub.calls[0] == ("habitat/v1/cmd/vitals-1", b'{"v":1,"cmd":"alarm","on":true}', 1, True)
    r.send("vitals-1", Command(1, "tare"))
    assert pub.calls[1][3] is False
    CommandRouter(None, None).send("exercise-1", Command(1, "tare"))


def test_router_sends_cabin_commands_over_the_serial_link(settings):
    # D40: cabin-1 is the UNO's DHT11, on the same USB serial link as exercise-1. Nothing
    # subscribes to habitat/v1/cmd/cabin-1, so an MQTT publish there was silently lost.
    link, pub = rig(settings), Pub()
    CommandRouter(link, pub).send("cabin-1", Command(1, "alarm", on=True))
    assert link._port.writes == [b'{"v":1,"cmd":"alarm","on":true}\n']
    assert pub.calls == []


def test_cli_topic_for_serial_nodes_is_the_rig_topic():
    # The hub bridges only habitat/v1/cmd/exercise-1 to the serial link.
    assert command_topic("cabin-1") == "habitat/v1/cmd/exercise-1"
    assert command_topic("exercise-1") == "habitat/v1/cmd/exercise-1"
    assert command_topic("vitals-1") == "habitat/v1/cmd/vitals-1"


def test_mqtt_bridge(settings, tmp_path, clock, caplog):
    from hub.ingest import Ingestor
    from hub.mqtt import NodeRegistry
    from hub.store import Store

    link = rig(settings)
    ing, nodes = Ingestor(Store(tmp_path / "c.db"), clock), NodeRegistry(clock)
    handlers = {"cmd": lambda node, payload: link.send_raw(node, payload)}
    route_message(ing, nodes, "habitat/v1/cmd/exercise-1",
                  b'{"v":1,"cmd":"servo","angle_deg":30}', handlers)  # fmt: skip
    assert link._port.writes == [b'{"v":1,"cmd":"servo","angle_deg":30}\n']
    with caplog.at_level(logging.INFO):
        route_message(ing, nodes, "habitat/v1/cmd/exercise-1", b'{"v":1,"cmd":"servo"}', handlers)
    assert len(link._port.writes) == 1
