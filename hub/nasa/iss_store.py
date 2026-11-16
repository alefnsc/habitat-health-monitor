"""ISS Live items stored as reference readings (D45 §4.2). Units come from isslive_routes.UNITS,
the table the ISS cabin route already serves, so the stored values match what the console shows."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from hub.contract import INDICATORS, Reading
from hub.nasa.isslive import ISS_ITEMS, IssItemUpdate
from hub.nasa.isslive_routes import MMHG_TO_HPA, UNITS

log = logging.getLogger("hub.nasa.iss_store")

NODE = "nasa"
DEV = "ISSLIVE"
MIN_GAP = timedelta(minutes=1)  # at most one row per item per minute
FRESH = timedelta(minutes=10)  # an item older than this when it arrives is not stored
AHEAD = timedelta(minutes=2)  # an item stamped further ahead than this is a bad clock: skipped
# ISS item name -> hub indicator. The Lab and Node 3 ppCO2 items are two modules at different
# levels: one series of both would move with the update mix alone, so each has its own indicator.
IND_FOR: dict[str, str] = {
    "cabin_pressure": "iss_cabin_p",
    "cabin_temperature": "iss_cabin_temp",
    "lab_ppco2": "iss_ppco2",
    "node3_ppco2": "iss_ppco2_node3",
}


def to_hub_unit(name: str, val: float) -> float:
    """The ISS value in the hub indicator's unit: pressure mmHg -> hPa; the others unchanged."""
    if IND_FOR[name] == "iss_cabin_p" and UNITS[name] == "mmHg":
        return round(val * MMHG_TO_HPA, 2)
    return val


class IssWriter:
    """IssLiveClient's on_update callback: one internal reading per fresh item update."""

    def __init__(self, ingest: Callable[[Reading], object], *, boot: int) -> None:
        self.ingest = ingest
        self.boot = boot
        self._seq = 0
        self._last: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def on_update(self, u: IssItemUpdate) -> bool:
        """True when a reading was handed to the ingestor."""
        name = ISS_ITEMS.get(u.item)
        if name not in IND_FOR:
            return False
        if u.received_at - u.measured_at > FRESH:
            return False
        if u.measured_at - u.received_at > AHEAD:
            return False  # a future stamp would also block the item's next updates (MIN_GAP)
        with self._lock:
            last = self._last.get(u.item)
            if last is not None and u.measured_at - last < MIN_GAP:
                return False
            self._last[u.item] = u.measured_at
            self._seq += 1
            seq = self._seq
        age_ms = max(0, int((u.received_at - u.measured_at).total_seconds() * 1000))
        ind = IND_FOR[name]
        r = Reading(
            v=1, node=NODE, boot=self.boot, seq=seq, age_ms=age_ms, ind=ind,
            val=to_hub_unit(name, u.val), unit=INDICATORS[ind], src="nasa", dev=DEV, q=("ok",),
            crew=None, code=None,
        )  # fmt: skip
        try:
            self.ingest(r)
        except Exception:
            log.exception("iss reading %s failed", ind)
            return False
        return True
