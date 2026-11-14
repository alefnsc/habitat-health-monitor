"""ISS Live Lightstreamer client (N8c). Drives IssLiveState; reconnects on its own."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from hub.nasa.isslive import ISS_ITEMS, IssItemUpdate, IssLiveState

log = logging.getLogger("hub.nasa.isslive")

FIELDS = ["TimeStamp", "Value", "Status.Class"]
FORBIDDEN_ITEM = "TIME_000001"  # about 20 updates per second: never subscribe


def _z(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _ItemListener:
    def __init__(self, owner: IssLiveClient) -> None:
        self._owner = owner

    def onItemUpdate(self, update) -> None:  # noqa: N802
        self._owner.handle_update(
            update.getItemName(),
            update.getValue("TimeStamp"),
            update.getValue("Value"),
            update.getValue("Status.Class"),
        )

    def __getattr__(self, name: str):
        # The library calls many optional callbacks; ignore the ones we do not use.
        if name.startswith("on"):
            return lambda *a, **k: None
        raise AttributeError(name)


class _StatusListener:
    def __init__(self, owner: IssLiveClient) -> None:
        self._owner = owner

    def onStatusChange(self, status: str) -> None:  # noqa: N802
        self._owner.handle_status(status)

    def __getattr__(self, name: str):
        if name.startswith("on"):
            return lambda *a, **k: None
        raise AttributeError(name)


class IssLiveClient:
    def __init__(
        self,
        items: list[str],
        state: IssLiveState,
        *,
        server: str = "https://push.lightstreamer.com",
        adapter_set: str = "ISSLIVE",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        on_update: Callable[[IssItemUpdate], None] | None = None,
    ) -> None:
        if FORBIDDEN_ITEM in items:
            raise ValueError(f"{FORBIDDEN_ITEM} must never be subscribed")
        self.items = list(items)
        self.state = state
        self.server = server
        self.adapter_set = adapter_set
        self._clock = clock
        self._on_update = on_update
        self.listener = _ItemListener(self)
        self.status_listener = _StatusListener(self)
        self._ls = None
        self._sub = None

    def handle_update(
        self, item: str, raw_ts: str | None, raw_val: str | None, status_class: str | None
    ) -> None:
        now = self._clock()
        if self.state.update(item, raw_ts or "", raw_val, status_class, now) and self._on_update:
            self._on_update(self.state.latest()[item])

    def handle_status(self, status: str) -> None:
        up = status.startswith("CONNECTED")
        self.state.connected = up
        if up:
            self.state.last_connected_at = self._clock()
        log.info("iss live status %s", status)

    def start(self) -> None:
        from lightstreamer.client import LightstreamerClient, Subscription

        self.state.started_at = self._clock()
        self._ls = LightstreamerClient(self.server, self.adapter_set)
        self._ls.addListener(self.status_listener)
        self._sub = Subscription("MERGE", self.items, FIELDS)
        self._sub.addListener(self.listener)
        self._ls.subscribe(self._sub)
        self._ls.connect()

    def stop(self) -> None:
        if self._ls is None:
            return
        if self._sub is not None:
            self._ls.unsubscribe(self._sub)
        self._ls.disconnect()
        self._ls = None


def record_capture(path: Path, updates: Iterable[IssItemUpdate]) -> int:
    """Append updates as JSON lines; returns the number written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for u in updates:
            f.write(
                json.dumps(
                    {
                        "item": u.item,
                        "val": u.val,
                        "ts": u.ts,
                        "status_class": u.status_class,
                        "received_at": _z(u.received_at),
                    }
                )
                + "\n"
            )
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hub.nasa.isslive_client")
    ap.add_argument("--items", default=",".join(ISS_ITEMS))
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--record", type=Path, default=None)
    ap.add_argument("--minutes", type=float, default=30.0)
    a = ap.parse_args(argv)
    duration = a.minutes * 60 if a.record else (a.seconds or 60.0)
    state = IssLiveState()

    def on_update(u: IssItemUpdate) -> None:
        age = (u.received_at - u.measured_at).total_seconds()
        print(f"{u.item} {ISS_ITEMS.get(u.item, '?')} val={u.val} age_s={age:.0f}", flush=True)
        if a.record:
            record_capture(a.record, [u])

    client = IssLiveClient(a.items.split(","), state, on_update=on_update)
    client.start()
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
    print(f"done; items seen: {sorted(state.latest())}", file=sys.stderr)
    return 0 if state.latest() else 1


if __name__ == "__main__":
    raise SystemExit(main())
