"""Docker wiring (D47): plain text checks on .dockerignore, the Dockerfile and compose.yaml."""

import fnmatch
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# `python -m pkg.mod` in shell form, and "python", "-m", "pkg.mod" in exec form.
SHELL_FORM = re.compile(r"\bpython -m ([A-Za-z_][\w.]*)")
EXEC_FORM = re.compile(r'"python",\s*"-m",\s*"([A-Za-z_][\w.]*)"')


def _ignore_lines() -> set[str]:
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    return {ln.strip().rstrip("/") for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


def _modules(text: str) -> set[str]:
    return set(SHELL_FORM.findall(text)) | set(EXEC_FORM.findall(text))


def _module_exists(name: str) -> bool:
    parts = name.split(".")
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())
    finder = py["tool"]["setuptools"]["packages"]["find"]
    packaged = any(fnmatch.fnmatch(parts[0], pat) for pat in finder["include"])
    for where in finder["where"]:
        base = ROOT / where / Path(*parts)
        if packaged and ((base / "__main__.py").is_file() or base.with_suffix(".py").is_file()):
            return True
    return False


def test_dockerignore_keeps_secrets_and_state_out():
    ignored = _ignore_lines()
    for entry in (".env", "var", "hub/mosquitto/passwd"):
        assert entry in ignored, entry
    assert "!.env" not in ignored and "!hub/mosquitto/passwd" not in ignored


def test_every_python_module_in_docker_files_exists_and_is_packaged():
    found: dict[str, set[str]] = {}
    for name in ("Dockerfile", "compose.yaml"):
        found[name] = _modules((ROOT / name).read_text())
    assert {"hub", "hub.sim", "linksim", "receiver"} <= found["compose.yaml"]
    assert "hub" in found["Dockerfile"]
    missing = sorted(m for mods in found.values() for m in mods if not _module_exists(m))
    assert not missing, missing


def test_module_check_rejects_a_missing_module():
    assert not _module_exists("hub.nope")
    assert not _module_exists("tools.vault")  # in the repo, but not installed in the image
