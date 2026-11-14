"""Shared NASA app state (task N4). H19 sets `app.state.nasa = NasaState(...)`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request

from hub.nasa.config import NasaSettings
from hub.nasa.donki_cache import DonkiCache


@dataclass
class NasaState:
    settings: NasaSettings
    cache: DonkiCache
    clock: Callable[[], datetime]
    crews: tuple[str, ...]
    policy: Any | None = None  # ActuatorPolicy (N5)
    iss: Any | None = None  # IssLiveState (N8b)
    dose: Any | None = None  # DoseWriter (N7a)


def get_nasa_state(request: Request) -> NasaState:
    return request.app.state.nasa
