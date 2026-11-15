"""Secret runner (D44): run a command with secrets from the team's key vault in its environment.

    python -m tools.vault run -- <command> ...
    python -m tools.vault check

Settings come from the environment, or from .env for any that are unset:
  VAULT_NAME  the key vault's name
  VAULT_MAP   comma-separated ENV_NAME=secret-name pairs

Each value is read with `az keyvault secret show` and handed only to the child command's environment.
A value is never printed, logged or written to disk. `check` uses `az keyvault secret list`, which returns
metadata only. The vault and secret names stay in the git-ignored .env, out of the repository.
Import-time tools only: the habitat core never needs the vault.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

Runner = Callable[[list[str]], tuple[int, str]]
Spawn = Callable[[list[str], dict[str, str]], int]

KEYS = ("VAULT_NAME", "VAULT_MAP")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SECRET_NAME = re.compile(r"^[0-9A-Za-z-]{1,127}$")


class VaultError(Exception):
    pass


def _az(args: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, ""
    return p.returncode, p.stdout


def _spawn(cmd: list[str], env: dict[str, str]) -> int:
    try:
        return subprocess.call(cmd, env=env)
    except FileNotFoundError:
        print(f"vault: command not found: {cmd[0]}", file=sys.stderr)
        return 127


def read_dotenv(path: Path) -> dict[str, str]:
    """VAULT_* lines from a .env file. Nothing else is read."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() in KEYS:
            out[k.strip()] = v.strip().strip("'\"")
    return out


def config(environ: Mapping[str, str], dotenv: Path) -> tuple[str, list[tuple[str, str]]]:
    merged = {**read_dotenv(dotenv), **{k: environ[k] for k in KEYS if environ.get(k)}}
    vault = merged.get("VAULT_NAME", "")
    if not vault:
        raise VaultError("set VAULT_NAME (environment or .env)")
    return vault, parse_map(merged.get("VAULT_MAP", ""))


def parse_map(raw: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        env_name, sep, secret = (s.strip() for s in part.partition("="))
        if not sep or not ENV_NAME.match(env_name) or not SECRET_NAME.match(secret):
            raise VaultError(f"VAULT_MAP entry is not ENV_NAME=secret-name: {env_name or part!r}")
        if any(e == env_name for e, _ in pairs):
            raise VaultError(f"VAULT_MAP names {env_name} twice")
        pairs.append((env_name, secret))
    if not pairs:
        raise VaultError("set VAULT_MAP to ENV_NAME=secret-name pairs (environment or .env)")
    return pairs


def fetch(vault: str, pairs: Sequence[tuple[str, str]], runner: Runner) -> dict[str, str]:
    values: dict[str, str] = {}
    for env_name, secret in pairs:
        args = ["az", "keyvault", "secret", "show", "--vault-name", vault, "--name", secret,
                "--query", "value", "-o", "tsv"]  # fmt: skip
        code, out = runner(args)
        value = out.rstrip("\r\n") if code == 0 else ""
        if not value:
            raise VaultError(f"could not read {env_name} from the vault (az exit {code})")
        values[env_name] = value
    return values


def check(vault: str, pairs: Sequence[tuple[str, str]], runner: Runner) -> int:
    query = "[].{name:name,enabled:attributes.enabled,updated:attributes.updated}"
    code, out = runner(
        ["az", "keyvault", "secret", "list", "--vault-name", vault, "--query", query, "-o", "json"]
    )
    if code != 0:
        raise VaultError(f"could not list the vault (az exit {code})")
    rows = {r.get("name"): r for r in json.loads(out or "[]")}
    missing = 0
    for env_name, secret in pairs:
        r = rows.get(secret)
        if r is None:
            missing += 1
            print(f"{env_name}: missing")
        else:
            state = "enabled" if r.get("enabled") else "disabled"
            print(f"{env_name}: present ({state}, updated {r.get('updated')})")
    return 1 if missing else 0


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    runner: Runner = _az,
    spawn: Spawn = _spawn,
    dotenv: Path = Path(".env"),
) -> int:
    environ = os.environ if environ is None else environ
    ap = argparse.ArgumentParser(prog="python -m tools.vault", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a command with the mapped secrets in its environment")
    r.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("check", help="confirm each mapped secret exists (metadata only)")
    args = ap.parse_args(argv)
    command = list(getattr(args, "command", []) or [])
    if command[:1] == ["--"]:
        command = command[1:]
    try:
        if args.cmd == "run" and not command:
            raise VaultError(
                "give the command after --, for example: run -- python -m tools.food.fdc search oats"
            )
        vault, pairs = config(environ, dotenv)
        if args.cmd == "check":
            return check(vault, pairs, runner)
        values = fetch(vault, pairs, runner)
    except VaultError as e:
        print(f"vault: {e}", file=sys.stderr)
        return 2
    return spawn(command, {**environ, **values})


if __name__ == "__main__":
    raise SystemExit(main())
