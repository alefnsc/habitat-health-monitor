# ruff: noqa: TRY004  (the spec requires ValueError for every malformed entry)
"""Reference values file loader (NU9). Display only: no status is derived from it."""

from __future__ import annotations

import json
from pathlib import Path

KINDS = frozenset({"range", "upper", "floor", "average", "per_kg", "text"})
_REQUIRED = ("ind", "label", "kind", "unit", "value_text", "source_ref", "url")


def load_references(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"references file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"{path}: invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be an object")
    for f in ("source", "retrieved"):
        if not isinstance(data.get(f), str) or not data[f]:
            raise ValueError(f"{path}: missing {f}")
    if not isinstance(data.get("items"), list) or not isinstance(data.get("notes"), list):
        raise ValueError(f"{path}: items and notes must be lists")
    for it in data["items"]:
        name = it.get("ind", "?") if isinstance(it, dict) else "?"
        if not isinstance(it, dict):
            raise ValueError(f"reference entry {name}: not an object")
        for f in _REQUIRED:
            if not isinstance(it.get(f), str) or not it[f]:
                raise ValueError(f"reference entry {name}: missing {f}")
        if it["kind"] not in KINDS:
            raise ValueError(f"reference entry {name}: unknown kind {it['kind']!r}")
        if not isinstance(it.get("has_rule"), bool):
            raise ValueError(f"reference entry {name}: has_rule must be true or false")
        for f in ("low", "high"):
            v = it.get(f)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise ValueError(f"reference entry {name}: {f} must be a number or null")
    return data
