"""Link-state proxy of the link simulator (H21, D16)."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

import httpx

from hub.config import Settings

log = logging.getLogger("hub.link")

STATES = ("contact", "blackout", "unreachable")
DEFAULT_LIGHT_TIME_S = 720
DEFAULT_TIME_SCALE = 60
TIMEOUT_S = 1.0


def fallback_state(path: Path) -> dict:
    light, scale = DEFAULT_LIGHT_TIME_S, DEFAULT_TIME_SCALE
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            light = cfg.get("light_time_s", light)
            scale = cfg.get("time_scale", scale)
    except (OSError, ValueError):
        pass
    return {
        "state": "unreachable", "light_time_s": light, "time_scale": scale,
        "queue_len": 0, "last_blackout": None,
    }  # fmt: skip


def _num(x: object) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _valid(body: object) -> bool:
    if not isinstance(body, dict) or body.get("state") not in STATES:
        return False
    if not (_num(body.get("light_time_s")) and _num(body.get("time_scale"))):
        return False
    if not isinstance(body.get("queue_len"), int):
        return False
    lb = body.get("last_blackout")
    if lb is None:
        return True
    return (
        isinstance(lb, dict)
        and isinstance(lb.get("start"), str)
        and (lb.get("end") is None or isinstance(lb.get("end"), str))
    )


def fetch_link_state(client: httpx.Client, base_url: str, fallback_path: Path) -> dict:
    if base_url:
        try:
            r = client.get(f"{base_url.rstrip('/')}/link/state", timeout=TIMEOUT_S)
            r.raise_for_status()
            body = r.json()
            if _valid(body):
                return {
                    k: body[k]
                    for k in ("state", "light_time_s", "time_scale", "queue_len", "last_blackout")
                }
            log.warning("linksim returned a malformed link state: %.120s", r.text)
        except (httpx.HTTPError, ValueError) as e:
            log.debug("linksim unreachable: %s", e)
    return fallback_state(fallback_path)


class LinkWatcher:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client,
        publish: Callable[[str, dict], None],
        interval_s: float = 2.0,
    ) -> None:
        self.settings, self.client, self.publish, self.interval_s = (
            settings,
            client,
            publish,
            interval_s,
        )
        self._last: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> dict:
        body = fetch_link_state(self.client, self.settings.linksim_url, self.settings.link_config)
        if body != self._last:
            self._last = body
            self.publish("link", body)
        return body

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                log.exception("link poll failed")
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="link-watcher", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
