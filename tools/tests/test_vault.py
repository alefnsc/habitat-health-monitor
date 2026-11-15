"""Secret runner (D44 P1). A fake `az` stands in for the key vault; no test touches a real vault."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import vault

SECRET = "not-a-real-value-123"


class FakeAz:
    """Records every az call. `show` returns SECRET for known names; `list` returns metadata only."""

    def __init__(self, known=("fdc-key",), fail=False):
        self.calls: list[list[str]] = []
        self.known = set(known)
        self.fail = fail

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(args)
        if self.fail:
            return 1, ""
        if args[:3] == ["az", "keyvault", "secret"] and args[3] == "show":
            name = args[args.index("--name") + 1]
            return (0, SECRET + "\n") if name in self.known else (3, "")
        if args[:4] == ["az", "keyvault", "secret", "list"]:
            rows = [
                {"name": n, "enabled": True, "updated": "2026-11-14T06:23:15+00:00"}
                for n in self.known
            ]
            return 0, json.dumps(rows)
        return 9, ""


class FakeSpawn:
    def __init__(self, code=0):
        self.code = code
        self.cmd: list[str] | None = None
        self.env: dict[str, str] | None = None

    def __call__(self, cmd: list[str], env: dict[str, str]) -> int:
        self.cmd, self.env = cmd, env
        return self.code


ENV = {"VAULT_NAME": "test-vault", "VAULT_MAP": "USDA_FDC_API_KEY=fdc-key", "PATH": "/usr/bin"}


def run(argv, env=ENV, az=None, spawn=None, dotenv: Path | None = None):
    az = az or FakeAz()
    spawn = spawn or FakeSpawn()
    code = vault.main(
        argv, environ=env, runner=az, spawn=spawn, dotenv=dotenv or Path("/nonexistent/.env")
    )
    return code, az, spawn


def test_run_hands_the_secret_to_the_child_environment_only(capsys):
    code, _, spawn = run(["run", "--", "python", "-m", "tools.food.fdc", "search", "oats"])
    assert code == 0
    assert spawn.cmd == ["python", "-m", "tools.food.fdc", "search", "oats"]
    assert spawn.env["USDA_FDC_API_KEY"] == SECRET
    assert spawn.env["PATH"] == "/usr/bin"
    assert SECRET not in " ".join(spawn.cmd)
    out = capsys.readouterr()
    assert SECRET not in out.out and SECRET not in out.err


def test_run_reads_the_value_with_az_show(capsys):
    _, az, _ = run(["run", "--", "true"])
    assert az.calls == [
        ["az", "keyvault", "secret", "show", "--vault-name", "test-vault", "--name", "fdc-key",
         "--query", "value", "-o", "tsv"],
    ]  # fmt: skip


def test_run_returns_the_child_exit_code():
    code, _, _ = run(["run", "--", "false"], spawn=FakeSpawn(code=7))
    assert code == 7


def test_az_failure_names_the_variable_only_and_runs_nothing(capsys):
    code, _, spawn = run(["run", "--", "true"], az=FakeAz(fail=True))
    assert code == 2
    assert spawn.cmd is None
    err = capsys.readouterr().err
    assert "USDA_FDC_API_KEY" in err and "exit 1" in err
    assert "fdc-key" not in err and "test-vault" not in err


def test_missing_config_stops_before_any_az_call(capsys):
    code, az, spawn = run(["run", "--", "true"], env={"PATH": "/usr/bin"})
    assert code == 2 and az.calls == [] and spawn.cmd is None
    assert "VAULT_NAME" in capsys.readouterr().err


def test_run_without_a_command_is_refused(capsys):
    code, az, _ = run(["run"])
    assert code == 2 and az.calls == []


def test_config_comes_from_dotenv_and_the_environment_wins(tmp_path: Path):
    dot = tmp_path / ".env"
    dot.write_text(
        "# vault\nVAULT_NAME=dot-vault\nVAULT_MAP='USDA_FDC_API_KEY=fdc-key'\nRING_CLIENT_ID=x\n",
        encoding="utf-8",
    )
    _, az, _ = run(["run", "--", "true"], env={"PATH": "/usr/bin"}, dotenv=dot)
    assert az.calls[0][az.calls[0].index("--vault-name") + 1] == "dot-vault"
    _, az, _ = run(["run", "--", "true"], env={"VAULT_NAME": "env-vault"}, dotenv=dot)
    assert az.calls[0][az.calls[0].index("--vault-name") + 1] == "env-vault"


@pytest.mark.parametrize("raw", ["USDA_FDC_API_KEY", "lower=fdc-key", "A=bad name", "A=x,A=y", ""])
def test_bad_maps_are_refused(raw, capsys):
    code, az, _ = run(["run", "--", "true"], env={**ENV, "VAULT_MAP": raw})
    assert code == 2 and az.calls == []


def test_two_pairs_reach_the_child():
    env = {**ENV, "VAULT_MAP": "RING_CLIENT_ID=ring-id, RING_CLIENT_SECRET=ring-secret"}
    _, _, spawn = run(["run", "--", "true"], env=env, az=FakeAz(known=("ring-id", "ring-secret")))
    assert spawn.env["RING_CLIENT_ID"] == SECRET and spawn.env["RING_CLIENT_SECRET"] == SECRET


def test_check_uses_metadata_only(capsys):
    env = {**ENV, "VAULT_MAP": "USDA_FDC_API_KEY=fdc-key,RING_CLIENT_ID=ring-id"}
    code, az, spawn = run(["check"], env=env)
    assert code == 1  # one is missing
    assert all("show" not in c for c in az.calls)
    assert spawn.cmd is None
    out = capsys.readouterr().out
    assert "USDA_FDC_API_KEY: present" in out and "RING_CLIENT_ID: missing" in out
    assert SECRET not in out and "fdc-key" not in out
