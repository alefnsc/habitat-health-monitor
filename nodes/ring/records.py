"""Pull records as JSONL: one raw pull per line, kept private (mode 600) so it can be replayed (D41 §3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

KIND = "ring_pull"


def load_records(path: Path) -> list[dict]:
    """Every `ring_pull` line of a JSONL file; other kinds (such as a `note` header) are skipped."""
    out: list[dict] = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as e:
            raise ValueError(f"{path}:{n}: not JSON ({e})") from None
        if isinstance(obj, dict) and obj.get("kind") == KIND:
            out.append(obj)
    return out


def append_record(path: Path, record: dict) -> None:
    """Append one record; the folder is created 700 and the file 600."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (json.dumps({**record, "kind": KIND}, separators=(",", ":")) + "\n").encode())
    finally:
        os.close(fd)
