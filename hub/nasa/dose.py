"""Mission dose estimate and rad_dose_cum readings (task N7a).

Effective dose here is an estimate: the profile's rate times the mission day, with the
method string copied verbatim from the Science lane's file. It is never derived from OSDR
absorbed mGy, and the two are never added.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from hub.contract import Reading

if TYPE_CHECKING:
    from hub.ingest import Ingestor


@dataclass(frozen=True)
class DoseProfile:
    profile: str
    mission_start: date
    rate_msv_per_day: float
    rate_ref: str
    rate_url: str
    method: str
    career_limit_msv: float
    career_limit_ref: str


@dataclass(frozen=True)
class DoseEstimate:
    profile: str
    mission_day: int
    rate_msv_per_day: float
    effective_msv: float
    effective_msv_method: str
    career_limit_msv: float
    career_fraction: float


def load_dose_profile(path: Path) -> DoseProfile:
    raw = json.loads(Path(path).read_text())
    for key in ("rate_ref", "method"):
        if not str(raw.get(key, "")).strip():
            raise ValueError(f"dose profile needs a non-empty {key}")
    return DoseProfile(
        profile=raw["profile"],
        mission_start=date.fromisoformat(raw["mission_start"]),
        rate_msv_per_day=float(raw["rate_msv_per_day"]),
        rate_ref=raw["rate_ref"],
        rate_url=raw.get("rate_url", ""),
        method=raw["method"],
        career_limit_msv=float(raw["career_limit_msv"]),
        career_limit_ref=raw.get("career_limit_ref", ""),
    )


def mission_day(today: date, start: date) -> int:
    """Day 1 is the start date; 0 before the start."""
    return max(0, (today - start).days + 1) if today >= start else 0


def estimate_dose(p: DoseProfile, today: date) -> DoseEstimate:
    day = mission_day(today, p.mission_start)
    msv = round(day * p.rate_msv_per_day, 4)
    return DoseEstimate(
        profile=p.profile,
        mission_day=day,
        rate_msv_per_day=p.rate_msv_per_day,
        effective_msv=msv,
        effective_msv_method=p.method,
        career_limit_msv=p.career_limit_msv,
        career_fraction=round(msv / p.career_limit_msv, 4),
    )


class DoseWriter:
    def __init__(self, profile: DoseProfile, ingestor: Ingestor | None) -> None:
        self.profile = profile
        self.ingestor = ingestor
        self.last: DoseEstimate | None = None
        self.last_status: Literal["ok", "watch", "act", "unknown"] = "unknown"
        self._written_day: int | None = None

    async def tick(self, now: datetime) -> None:
        est = estimate_dose(self.profile, now.astimezone(UTC).date())
        self.last = est
        if self.ingestor is None:
            self.last_status = "unknown"
            return
        if self._written_day == est.mission_day:
            return
        reading = Reading(
            v=1,
            node="nasa",
            boot=0,
            seq=int(now.timestamp() * 1000),
            age_ms=0,
            ind="rad_dose_cum",
            val=est.effective_msv,
            unit="mSv",
            src="nasa",
            dev="OSDR",
            q=("ok",),
            crew=None,
            code=None,
        )
        res = self.ingestor.ingest_internal(reading)
        self._written_day = est.mission_day
        entry = next((e for e in res.results if e.ind == "rad_dose_cum"), None)
        self.last_status = entry.status if entry is not None else "unknown"  # type: ignore[assignment]
