# linksim/consent.py
"""Consent boundary: decides which crossed-link items may go to the public ground segment."""

from __future__ import annotations

from hub.contract import BODY_INDS, CABIN_INDS, INTAKE_INDS

from .engine import OutboxItem

NASA_INDS: frozenset[str] = frozenset({"space_weather", "rad_dose_cum"})
SYNTHETIC_NODES: frozenset[str] = frozenset({"sim-1"})
PERSONAL_INDS: frozenset[str] = BODY_INDS | INTAKE_INDS


def parse_crews(raw: str | None) -> frozenset[str]:
    return frozenset(c.strip() for c in (raw or "").split(",") if c.strip())


def is_public(item: OutboxItem, public_crews: frozenset[str], public_reps: bool) -> bool:
    p = item.payload
    if p.get("node") in SYNTHETIC_NODES:
        return True
    if item.kind == "rep":
        return public_reps
    if item.kind == "prompt_answer":
        return p.get("crew") in public_crews
    if item.kind in ("reading", "alert"):
        ind = p.get("ind")
        if ind in CABIN_INDS or ind in NASA_INDS:
            return True
        if ind in PERSONAL_INDS:
            return p.get("crew") in public_crews
    return False


def filter_items(
    items: list[OutboxItem], public_crews: frozenset[str], public_reps: bool = False
) -> list[OutboxItem]:
    return [i for i in items if is_public(i, public_crews, public_reps)]
