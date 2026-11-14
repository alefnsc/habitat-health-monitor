"""Space-weather level evaluation (task N3).

The trigger logic is the team's own, not a NASA or NOAA product. It maps DONKI events to the
`space_weather` level (0 ok, 1 watch, 2 act). The hub then assesses that level with rule
`radiation_spe`. Nothing here reads data/thresholds.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from hub.nasa.donki import parse_time

RULE_ID = "radiation_spe"
WINDOW = timedelta(hours=24)
KP_WATCH = 7  # NOAA G3
Trigger = Literal["sep", "flare_x", "gst_kp7"]


def parse_donki_time(s: str) -> datetime:
    return parse_time(s)


@dataclass(frozen=True)
class SpaceWeatherAlert:
    status: Literal["ok", "watch", "act", "unknown"]
    level: int | None
    rule_id: str = RULE_ID
    trigger: Trigger | None = None
    reason: str = ""
    event_id: str | None = None
    event_time: datetime | None = None
    link: str | None = None


@dataclass(frozen=True)
class DonkiReplay:
    recorded_at: datetime
    source_url: str
    replay_now: datetime
    events: dict[str, list[dict]]


def load_replay(path: Path) -> DonkiReplay:
    raw = json.loads(Path(path).read_text())
    return DonkiReplay(
        recorded_at=parse_donki_time(raw["recorded_at"]),
        source_url=raw["source_url"],
        replay_now=parse_donki_time(raw["replay_now"]),
        events=raw["events"],
    )


def _recent(ts: str | None, now: datetime) -> datetime | None:
    if not ts:
        return None
    t = parse_donki_time(ts)
    return t if now - WINDOW <= t <= now else None


def _fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC")


def evaluate_space_weather(
    events: dict[str, list[dict] | None], now: datetime
) -> SpaceWeatherAlert:
    flr, sep, gst = events.get("FLR"), events.get("SEP"), events.get("GST")
    if flr is None or sep is None or gst is None:
        return SpaceWeatherAlert("unknown", None, reason="DONKI data is not available yet.")

    hits = [(t, e) for e in sep if (t := _recent(e.get("eventTime"), now))]
    if hits:
        t, e = max(hits, key=lambda h: h[0])
        return SpaceWeatherAlert(
            "act",
            2,
            trigger="sep",
            event_id=e.get("sepID"),
            event_time=t,
            link=e.get("link"),
            reason=f"Solar energetic particle event reported at {_fmt(t)}.",
        )
    hits = [
        (t, e)
        for e in flr
        if str(e.get("classType", "")).upper().startswith("X")
        and (t := _recent(e.get("peakTime"), now))
    ]
    if hits:
        t, e = max(hits, key=lambda h: h[0])
        return SpaceWeatherAlert(
            "watch",
            1,
            trigger="flare_x",
            event_id=e.get("flrID"),
            event_time=t,
            link=e.get("link"),
            reason=f"X-class solar flare ({e.get('classType')}) peaked at {_fmt(t)}.",
        )
    kp_hits = []
    for g in gst:
        for k in g.get("allKpIndex") or []:
            t = _recent(k.get("observedTime"), now)
            if t and float(k.get("kpIndex", 0)) >= KP_WATCH:
                kp_hits.append((t, g, k))
    if kp_hits:
        t, g, k = max(kp_hits, key=lambda h: h[0])
        return SpaceWeatherAlert(
            "watch",
            1,
            trigger="gst_kp7",
            event_id=g.get("gstID"),
            event_time=t,
            link=g.get("link"),
            reason=f"Geomagnetic storm reached Kp {k['kpIndex']} at {_fmt(t)}.",
        )
    return SpaceWeatherAlert(
        "ok", 0, reason="No qualifying space-weather event in the last 24 hours."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print the current space-weather level.")
    ap.add_argument("--replay", type=Path)
    args = ap.parse_args(argv)
    if args.replay:
        rp = load_replay(args.replay)
        a = evaluate_space_weather(rp.events, rp.replay_now)
    else:
        from hub.nasa.config import load_nasa_settings
        from hub.nasa.donki_cache import DonkiCache

        cache = DonkiCache(load_nasa_settings(os.environ).var_dir / "nasa")
        ev = {k: (c.events if (c := cache.read(k)) else None) for k in ("FLR", "SEP", "GST")}
        a = evaluate_space_weather(ev, datetime.now(UTC))
    print(a.status, a.level, a.rule_id, a.trigger, a.event_time.isoformat() if a.event_time else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
