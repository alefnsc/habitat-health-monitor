import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "nasa" / "isslive-probe.md"
EXPECTED = {
    "USLAB000058": "cabin_pressure",
    "USLAB000059": "cabin_temperature",
    "USLAB000055": "lab_ppco2",
    "NODE3000003": "node3_ppco2",
}


def test_items_recorded():
    rows = re.findall(r"^\| `([A-Z0-9_]+)` \| `(\w+)` \|", DOC.read_text(), re.MULTILINE)
    assert dict(rows) == EXPECTED


def test_unit_assumption():
    assert "mmHg by magnitude" in DOC.read_text()


def test_licence_line():
    lines = re.findall(r"^Licence: .* \(OSI: (yes|no)\)$", DOC.read_text(), re.MULTILINE)
    assert len(lines) == 1
