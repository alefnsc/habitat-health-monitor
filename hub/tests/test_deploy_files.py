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


def test_consent_doc_has_both_languages_and_rules():
    text = (ROOT / "docs" / "consent.md").read_text()
    for needle in ("## English", "## Português", "48 h", "PUBLIC_CREWS", "purge", "under 18", "menores de 18", "sim-1", "guardian", "Responsável legal"):
        assert needle in text, needle
    assert text.count("sim-1") >= 2


def test_deploy_public_doc_commands_match_code():
    text = (ROOT / "docs" / "deploy-public.md").read_text()
    for needle in (
        "GROUND_INGEST_SECRET",
        "UPSTASH_REDIS_REST_URL",
        "KV_REST_API_URL",
        "PUBLIC_GROUND_URL",
        "Never replay recordings of real people through node sim-1",
        '--ground ""',
        "public crews:",
        "PUBLIC_REPS=0",
        "5 Redis commands",
    ):
        assert needle in text, needle
    assert (ROOT / "linksim" / "link.demo.json").exists()
    assert (ROOT / "data" / "replay" / "l0-synthetic.jsonl").exists()
