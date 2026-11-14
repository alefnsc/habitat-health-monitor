"""Assessment result types and the worst-of status entry (spec 4.7, D2, D3, D25)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from hub.contract import INTAKE_INDS

if TYPE_CHECKING:
    from hub.store import StoredReading

SEVERITY: dict[str, int] = {"act": 3, "watch": 2, "ok": 1, "unknown": 0}


@dataclass(frozen=True)
class AssessmentResult:
    id: int
    reading_id: int
    ind: str
    val: float | None
    unit: str
    status: str
    rule_id: str | None
    source_kind: str | None
    source_ref: str | None
    guidance_id: str | None
    escalate_to: str
    measured_at: str
    crew: str | None


@dataclass(frozen=True)
class Alert:
    id: int
    ind: str
    status: str
    prev_status: str | None
    rule_id: str
    measured_at: str
    crew: str | None
    escalate_to: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StatusEntry:
    ind: str
    val: float | None
    unit: str
    status: str
    rule_id: str | None
    source_kind: str | None
    source_ref: str | None
    guidance_id: str | None
    escalate_to: str
    measured_at: str
    crew: str | None
    src: str
    dev: str
    q: list[str]
    node: str
    reading_id: int

    def to_dict(self) -> dict:
        return asdict(self)


def escalate_to_for(status: str, ind: str) -> str:
    """Status-based escalation fallback (D25)."""
    if status == "act":
        return "cmo" if ind in INTAKE_INDS else "flight_surgeon"
    if status == "watch":
        return "self" if ind in INTAKE_INDS else "cmo"
    return "self"


def entry_for(r: StoredReading, results: list[AssessmentResult]) -> StatusEntry:
    """One worst-of entry per reading; a flagged or rule-less reading is `unknown`."""
    common = {
        "src": r.src, "dev": r.dev, "q": list(r.q), "node": r.node, "reading_id": r.id,
    }  # fmt: skip
    if r.q != ("ok",) or not results:
        return StatusEntry(
            ind=r.ind, val=r.val, unit=r.unit, status="unknown", rule_id=None,
            source_kind=None, source_ref=None, guidance_id=None,
            escalate_to=escalate_to_for("unknown", r.ind), measured_at=r.measured_at,
            crew=r.crew, **common,
        )  # fmt: skip
    worst = results[0]
    for res in results[1:]:
        if SEVERITY[res.status] > SEVERITY[worst.status]:
            worst = res
    return StatusEntry(
        ind=r.ind, val=worst.val, unit=worst.unit, status=worst.status, rule_id=worst.rule_id,
        source_kind=worst.source_kind, source_ref=worst.source_ref,
        guidance_id=worst.guidance_id, escalate_to=worst.escalate_to,
        measured_at=r.measured_at, crew=r.crew, **common,
    )  # fmt: skip
