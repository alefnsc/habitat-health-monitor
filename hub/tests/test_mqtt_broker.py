import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.tests.helpers import msg

pytestmark = pytest.mark.broker


BENCH_PORT = 1883  # the live bench broker: this test must never connect or publish there


def broker_port() -> int | None:
    """Port of a throwaway anonymous broker named by HUB_TEST_BROKER_PORT and listening; never the bench's 1883.

    Opt-in on purpose: a plain `pytest` on the bench machine used to connect to the live broker as the hub's own
    client id and publish a synthetic cabin-1 reading there.
    """
    raw = os.environ.get("HUB_TEST_BROKER_PORT", "")
    if not raw.isdigit() or int(raw) == BENCH_PORT:
        return None
    try:
        socket.create_connection(("127.0.0.1", int(raw)), timeout=0.3).close()
    except OSError:
        return None
    return int(raw)


def test_broker_port_is_opt_in_and_never_the_bench(monkeypatch):
    monkeypatch.delenv("HUB_TEST_BROKER_PORT", raising=False)
    assert broker_port() is None
    monkeypatch.setenv("HUB_TEST_BROKER_PORT", str(BENCH_PORT))
    assert broker_port() is None


@pytest.mark.skipif(
    broker_port() is None,
    reason="set HUB_TEST_BROKER_PORT to a throwaway anonymous broker (never 1883)",
)
def test_broker_roundtrip(settings, clock):
    port = broker_port()
    s = replace(settings, mqtt_host="127.0.0.1", mqtt_port=port)
    pub = shutil.which("mosquitto_pub")
    assert pub, "mosquitto_pub missing"
    with TestClient(create_app(s, clock=clock)) as c:
        time.sleep(0.5)
        cmd = [
            pub,
            "-p",
            str(port),
            "-q",
            "1",
            "-t",
            "habitat/v1/r/cabin-1",
            "-m",
            json.dumps(msg()),
        ]
        subprocess.run(cmd, check=True, timeout=5)  # the throwaway test broker only
        deadline = time.time() + 2
        rows = []
        while time.time() < deadline and not rows:
            rows = c.get("/api/readings?ind=cabin_co2").json()
            time.sleep(0.1)
        assert rows and rows[0]["val"] == 812.0
