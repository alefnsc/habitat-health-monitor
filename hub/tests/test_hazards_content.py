"""S12: content tests for data/hazards.json."""

import json
from pathlib import Path
from urllib.parse import urlparse

from hub.contract import DERIVED, INDICATORS

ROOT = Path(__file__).resolve().parents[2]
HZ = {h["id"]: h for h in json.loads((ROOT / "data" / "hazards.json").read_text(encoding="utf-8"))}
FORBIDDEN = ["diagnos", "you have", "hypertension", "hypotension", "fever", "infection", "disease",
             "disorder", "depress", "tablet", "pill", "capsule", "dose of", "milligram", "mg "]  # fmt: skip


def test_hazards_five():
    assert set(HZ) == {"radiation", "isolation_confinement", "distance", "gravity",
                       "hostile_closed_environment"}  # fmt: skip


def test_hazard_has_indicator_and_url():
    for h in HZ.values():
        assert h["indicators_affected"]
        for ind in h["indicators_affected"]:
            assert ind in INDICATORS or ind in DERIVED, (h["id"], ind)
        host = urlparse(h["hrp_url"]).hostname or ""
        assert host == "nasa.gov" or host.endswith(".nasa.gov"), h["id"]


def test_hazard_text():
    for h in HZ.values():
        assert len(h["one_line_effect"]) <= 160
        for w in FORBIDDEN:
            assert w not in h["one_line_effect"].lower(), (h["id"], w)


def test_hazard_live_signals():
    s = {k: v["live_signal_ind"] for k, v in HZ.items()}
    assert set(s["radiation"]) == {"space_weather", "rad_dose_cum"}
    assert s["distance"] == "link" and s["gravity"] == "session_g"
    assert {"mood", "sleep_h"} <= set(s["isolation_confinement"])
    assert {"cabin_ppco2", "cabin_temp", "cabin_rh", "intake_water_ml"} <= set(
        s["hostile_closed_environment"]
    )
