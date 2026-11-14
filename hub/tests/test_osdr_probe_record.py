"""N6 Part A: the committed OSDR probe record is complete and its fixtures exist."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "docs" / "nasa" / "osdr-probe.md"
FIXTURES = ROOT / "hub" / "tests" / "fixtures"

REQUIRED_PATHS = [
    "/missions/",
    "/telemetry_data/",
    "/temperature/iss/",
    "/humidity/iss/",
    "/co2/iss/",
    "/temperature/ground/",
    "/humidity/ground/",
    "/co2/ground/",
    "/radiation_data/",
    "radlab/api/",
]


def _rows() -> list[list[str]]:
    rows = []
    for line in PROBE.read_text().splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def test_probe_rows_present():
    rows = _rows()
    for needle in REQUIRED_PATHS:
        matching = [r for r in rows if needle in r[0]]
        assert matching, f"no probe row for {needle}"
        assert any(re.fullmatch(r"\d{3}", r[1]) for r in matching), needle


def test_decision_lines():
    text = PROBE.read_text()
    missions = re.findall(r"^Mission: (\S.*)$", text, re.MULTILINE)
    assert len(missions) == 1 and missions[0].strip()
    sources = re.findall(r"^Radiation source: (\S+)$", text, re.MULTILINE)
    assert len(sources) == 1 and sources[0] in {"eda", "radlab"}
    confirmed = re.findall(r"^RadLab unit confirmed: (\S+)$", text, re.MULTILINE)
    assert len(confirmed) == 1 and confirmed[0] in {"yes", "no"}


def test_fixtures_exist():
    named = 0
    for row in _rows():
        cell = row[-1].strip("` ")
        if cell.endswith(".json"):
            path = FIXTURES / cell
            assert path.exists(), cell
            json.loads(path.read_text())
            named += 1
    assert named >= 10
