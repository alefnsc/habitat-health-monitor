"""Turn a logged meal into one reading per nutrient (NU2, NU4, NU6)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from hub.config import KNOWN_CREWS
from hub.contract import INTAKE_ORDER, INTAKE_UNITS, Reading
from hub.food.catalog import Catalog, nutrients_for
from hub.results import StatusEntry

MAX_ITEMS = 20
MAX_SERVINGS = 20.0
FUTURE_SLACK_S = 60
MAX_AGE = timedelta(hours=48)


class FoodError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class MealItem:
    food_id: str
    servings: float


@dataclass(frozen=True)
class MealRequest:
    crew: str | None
    items: list[MealItem]
    eaten_at: datetime | None = None


@dataclass
class MealResult:
    meal_id: int
    readings: list[tuple[str, int, bool]]  # (ind, reading id, duplicate)
    not_reported: list[str]
    results: list[StatusEntry]


class MealStore(Protocol):
    """The H agent's `Store` additions (H19): signatures assumed from the M6 plan text."""

    def insert_meal(
        self, crew: str | None, eaten_at: datetime, created_at: datetime, items: list[dict]
    ) -> int: ...


class _Ingestor(Protocol):
    def ingest_internal(self, r: Reading): ...


class FoodWriter:
    def __init__(
        self,
        store: MealStore,
        ingestor: _Ingestor,
        catalog: Catalog,
        clock: Callable[[], datetime],
        *,
        boot: int,
    ) -> None:
        self.store, self.ingestor, self.catalog, self.clock = store, ingestor, catalog, clock
        self.boot = boot
        self._seq = 0
        self._lock = threading.Lock()

    def _validate(self, req: MealRequest, now: datetime, eaten: datetime) -> None:
        if not req.items:
            raise FoodError("empty_meal")
        if len(req.items) > MAX_ITEMS:
            raise FoodError("too_many_items")
        for it in req.items:
            if it.food_id not in self.catalog.items:
                raise FoodError(f"unknown_food:{it.food_id}")
            if not 0 < it.servings <= MAX_SERVINGS:
                raise FoodError(f"bad_servings:{it.food_id}")
        if eaten > now + timedelta(seconds=FUTURE_SLACK_S):
            raise FoodError("bad_time")
        if eaten < now - MAX_AGE:
            raise FoodError("too_old")
        if req.crew is not None and req.crew not in KNOWN_CREWS:
            raise FoodError("bad_crew")

    def log_meal(self, req: MealRequest) -> MealResult:
        now = self.clock()
        eaten = (req.eaten_at or now).astimezone(UTC)
        self._validate(req, now, eaten)
        totals: dict[str, float | None] = dict.fromkeys(INTAKE_ORDER, 0.0)
        for it in req.items:
            for ind, v in nutrients_for(self.catalog.items[it.food_id], it.servings).items():
                totals[ind] = None if v is None or totals[ind] is None else totals[ind] + v
        age_ms = max(0, int((now - eaten).total_seconds() * 1000))
        readings: list[tuple[str, int, bool]] = []
        not_reported: list[str] = []
        results: list[StatusEntry] = []
        with self._lock:
            for ind in INTAKE_ORDER:
                val = totals[ind]
                if val is None:
                    not_reported.append(ind)
                    continue
                self._seq += 1
                res = self.ingestor.ingest_internal(
                    Reading(
                        v=1, node="food", boot=self.boot, seq=self._seq, age_ms=age_ms, ind=ind,
                        val=round(val, 2), unit=INTAKE_UNITS[ind], src="self", dev="catalog",
                        q=("ok",), crew=req.crew, code=None,
                    )
                )  # fmt: skip
                if res.stored is None:
                    raise FoodError(f"ingest_failed:{res.reason}")
                readings.append((ind, res.stored.id, res.duplicate))
                results.extend(res.results)
            meal_id = self.store.insert_meal(
                req.crew, eaten, now,
                [{"food_id": i.food_id, "servings": i.servings} for i in req.items],
            )  # fmt: skip
        return MealResult(meal_id, readings, not_reported, results)
