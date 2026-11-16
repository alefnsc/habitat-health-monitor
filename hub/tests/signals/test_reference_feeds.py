"""Reference feeds (D45 §4.2): stored, quiet, off /api/status, and usable by the signals."""

from datetime import timedelta

import pytest

from hub.assess import status_body
from hub.contract import REFERENCE_INDS, parse_reading
from hub.tests.helpers import T
from hub.tests.signals.kit import one, put_ref, real_rig


@pytest.fixture
def rig(tmp_path, clock):
    return real_rig(tmp_path, clock)


def test_contract_accepts_the_new_feeds():
    for ind, unit in (("earth_temp", "C"), ("earth_rh", "%"), ("earth_p", "hPa")):
        parse_reading({"v": 1, "node": "earth-1", "boot": 1, "seq": 1, "age_ms": 0, "ind": ind,
                       "val": 20, "unit": unit, "src": "ref", "dev": "WEATHER", "q": ["ok"]})  # fmt: skip
    assert REFERENCE_INDS == {
        "iss_cabin_p", "iss_cabin_temp", "iss_ppco2", "iss_ppco2_node3", "earth_temp", "earth_rh",
        "earth_p",
    }  # fmt: skip


def test_reference_feeds_are_quiet_and_off_status(rig):
    put_ref(rig, "earth_temp", 15.0, T, node="earth-1", dev="WEATHER", src="ref")
    assert rig.store.count("readings") == 1
    assert rig.store.count("outbox") == 0 and rig.store.count("assessments") == 0
    assert rig.events == []
    body = status_body(rig.store, [], None, T)
    assert all(r["ind"] not in REFERENCE_INDS for r in body["results"])


def test_iss_ppco2_trend_uses_the_cabin_builder(rig):
    for i in range(6 * 60):
        put_ref(rig, "iss_ppco2", 2.0 + 0.1 * i / 60, T - timedelta(minutes=6 * 60 - 1 - i),
                node="nasa", dev="ISSLIVE", src="nasa")  # fmt: skip
    s = one(rig, "iss_ppco2_6h", crew=None, at=T)
    assert s.headline_key == "signals.trend.up" and s.value.unit == "mmHg" and s.crew is None
