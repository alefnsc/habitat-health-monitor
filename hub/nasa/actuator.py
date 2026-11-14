"""Space-weather actuator policy (task N5).

Turns the evaluated space-weather state into (1) a `space_weather` reading through the normal
ingest pipeline, (2) servo and buzzer commands through `CommandRouter.send` (D7), and
(3) crew acknowledgement by RFID badge or console. With `router=None` (H14 cut) only the
readings and the acknowledgement work. This module builds no assessment results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from hub.contract import Reading
from hub.nasa.spaceweather import SpaceWeatherState, space_weather_state

try:  # H14 owns Command; a same-shaped fallback keeps N5 independent of the cut
    from hub.commands import Command
except ImportError:  # pragma: no cover - exercised only while H14 is absent

    @dataclass(frozen=True)
    class Command:  # type: ignore[no-redef]
        v: int
        cmd: str
        angle_deg: int | None = None
        on: bool | None = None
        mass_kg: float | None = None


if TYPE_CHECKING:
    from hub.ingest import Ingestor
    from hub.nasa.config import NasaSettings
    from hub.nasa.donki_cache import DonkiCache

log = logging.getLogger(__name__)

SERVO_ANGLE_DEG: dict[str, int] = {"ok": 30, "watch": 90, "act": 150, "unknown": 0}


class NoActiveAlert(Exception):
    """Acknowledgement attempted while no `act` alert is active."""


@dataclass(frozen=True)
class Ack:
    crew: str
    at: datetime
    event_id: str


def space_weather_reading(level: int, now: datetime, *, stale: bool) -> Reading:
    return Reading(
        v=1,
        node="nasa",
        boot=0,
        seq=int(now.timestamp() * 1000),
        age_ms=0,
        ind="space_weather",
        val=float(level),
        unit="level",
        src="nasa",
        dev="DONKI",
        q=("stale",) if stale else ("ok",),
        crew=None,
        code=None,
    )


class ActuatorPolicy:
    def __init__(
        self,
        router: Any | None,
        ingestor: Ingestor | None,
        *,
        settings: NasaSettings,
        cache: DonkiCache,
        crews: tuple[str, ...],
        rig_node: str = "exercise-1",
    ) -> None:
        self.router = router
        self.ingestor = ingestor
        self.settings = settings
        self.cache = cache
        self.crews = tuple(crews)
        self.rig_node = rig_node
        self.ack: Ack | None = None
        self._status: str | None = None
        self._event_id: str | None = None
        self._latched = False  # alarm is sounding and unacknowledged

    def _send(self, sent: list[Command], **fields: Any) -> None:
        if self.router is None:
            return
        cmd = Command(v=1, **fields)
        try:
            self.router.send(self.rig_node, cmd)
            sent.append(cmd)
        except Exception:
            log.exception("actuator command %s failed", fields.get("cmd"))

    def apply(self, state: SpaceWeatherState, now: datetime) -> list[Command]:
        sent: list[Command] = []
        status = state.alert.status

        if state.level is not None and self.ingestor is not None:
            try:
                self.ingestor.ingest_internal(
                    space_weather_reading(state.level, now, stale=state.stale)
                )
            except Exception:
                log.exception("space_weather reading failed")

        if status != self._status:
            self._send(sent, cmd="servo", angle_deg=SERVO_ANGLE_DEG[status])
            self._status = status

        if status == "act":
            event_id = state.alert.event_id or "unknown"
            if event_id != self._event_id:  # a new event re-arms the alarm
                self._event_id = event_id
                self.ack = None
                self._latched = True
                self._send(sent, cmd="alarm", on=True)
        elif status in ("ok", "watch"):
            if self._latched:
                self._send(sent, cmd="alarm", on=False)
            self._latched = False
            self._event_id = None
            self.ack = None
        # "unknown" (stale link) keeps a latched alarm sounding
        return sent

    async def tick(self, now: datetime) -> list[Command]:
        try:
            state = space_weather_state(now, settings=self.settings, cache=self.cache)
            return self.apply(state, now)
        except Exception:
            log.exception("actuator tick failed")
            return []

    def acknowledge(self, crew: str, now: datetime) -> Ack:
        return self._acknowledge(crew, now)[0]

    def _acknowledge(self, crew: str, now: datetime) -> tuple[Ack, list[Command]]:
        if crew not in self.crews:
            raise ValueError(f"unknown crew {crew!r}")
        if self._event_id is None:
            raise NoActiveAlert
        sent: list[Command] = []
        self.ack = Ack(crew, now.astimezone(UTC), self._event_id)
        if self._latched:
            self._latched = False
            self._send(sent, cmd="alarm", on=False)
        return self.ack, sent

    def on_badge(self, node: str, crew: str, now: datetime) -> list[Command]:
        try:
            return self._acknowledge(crew, now)[1]
        except (ValueError, NoActiveAlert):
            return []
