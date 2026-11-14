import json
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


def broker_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 1883), timeout=0.3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not broker_up(), reason="no broker on 127.0.0.1:1883")
def test_broker_roundtrip(settings, clock):
    s = replace(settings, mqtt_host="127.0.0.1")
    pub = shutil.which("mosquitto_pub")
    assert pub, "mosquitto_pub missing"
    with TestClient(create_app(s, clock=clock)) as c:
        time.sleep(0.5)
        cmd = [pub, "-q", "1", "-t", "habitat/v1/r/cabin-1", "-m", json.dumps(msg())]
        subprocess.run(cmd, check=True, timeout=5)  # an anonymous test broker; auth via env
        deadline = time.time() + 2
        rows = []
        while time.time() < deadline and not rows:
            rows = c.get("/api/readings?ind=cabin_co2").json()
            time.sleep(0.1)
        assert rows and rows[0]["val"] == 812.0
