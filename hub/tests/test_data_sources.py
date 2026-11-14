"""N11a: DATA_SOURCES.md covers every NASA file and the required hosts and notes."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8")


def test_every_nasa_file_listed():
    for p in sorted((ROOT / "data" / "nasa").glob("*")):
        if p.is_file() and p.name != ".gitkeep":
            assert p.relative_to(ROOT).as_posix() in TEXT, p.name


def test_hosts_listed():
    hosts = ["ccmc.gsfc.nasa.gov", "api.nasa.gov", "visualization.osdr.nasa.gov",
             "humanresearchroadmap.nasa.gov"]  # fmt: skip
    for h in hosts:
        assert h in TEXT
    if (ROOT / "docs" / "nasa" / "isslive-probe.md").exists():
        assert "push.lightstreamer.com" in TEXT  # ISS Live entry required once it is built


def test_donki_disclaimer():
    donki = TEXT.split("## NASA DONKI", 1)[1].split("\n## ", 1)[0]
    assert "NOAA SWPC" in donki and "research" in donki


def test_dose_units_named():
    osdr = TEXT.split("## NASA OSDR", 1)[1].split("\n## ", 1)[0]
    assert "mGy" in osdr
    dose = TEXT.split("## Mission dose estimate", 1)[1].split("\n## ", 1)[0]
    assert "mSv" in dose and "estimate" in dose
    profile = ROOT / "data" / "nasa" / "dose_profile.json"
    if profile.exists():
        assert json.loads(profile.read_text())["rate_ref"] in dose


def test_no_demo_key():
    assert "DEMO_KEY" not in TEXT


def test_no_key_in_file():
    for m in re.finditer(r"api_key=(\S+)", TEXT):
        assert m.group(1).startswith("<NASA_API_KEY>")


def test_fdc_entry():
    for s in ("FoodData Central", "CC0 1.0", "credit", "data/food/catalog.json"):
        assert s in TEXT


def test_nasa_nutrition_docs_listed():
    for s in ("JSC-67378", "NASA-STD-3001", "JSC-E-DAA-TN71711"):
        assert s in TEXT
