import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _names(lines):
    return {re.split(r"[<>=\[ ]", ln.strip())[0].lower() for ln in lines if ln.strip() and not ln.startswith("#")}


def test_function_requirements_match_pyproject():
    req = _names((ROOT / "api" / "requirements.txt").read_text().splitlines())
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())
    allowed = _names(py["project"]["dependencies"]) | _names(py["project"]["optional-dependencies"]["cloud"])
    assert {"fastapi", "upstash-redis"} <= req
    assert req <= allowed | {"pydantic"}


def test_vercel_json_routes_and_output():
    cfg = json.loads((ROOT / "vercel.json").read_text())
    assert cfg["framework"] is None
    assert cfg["outputDirectory"] == "ground/dist"
    assert {"source": "/ground/(.*)", "destination": "/api/index"} in cfg["rewrites"]
    assert "ground/receiver/**" in cfg["functions"]["api/index.py"]["includeFiles"]
    assert "build:public" in cfg["buildCommand"]


def test_no_provider_names_in_ui_sources():
    for path in list((ROOT / "ground" / "src").glob("*.ts")) + [ROOT / "ground" / "index.html"]:
        text = path.read_text().lower()
        assert "vercel" not in text and "upstash" not in text, path
