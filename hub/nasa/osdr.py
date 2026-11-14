"""OSDR Environmental Data Application snapshot fetcher (task N6).

Runs on the hub or by hand, never in the browser (OSDR sends no CORS headers). It fetches
one mission's ISS cabin series and radiation days once, summarises them and writes a
committed JSON snapshot. Decisions come from docs/nasa/osdr-probe.md.

Absorbed dose (mGy) is kept apart from effective dose (mSv). Effective dose is N7a's job.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Decisions recorded in docs/nasa/osdr-probe.md (proposed 2026-11-14, Science lane confirms).
MISSION = "RR-6"
RADIATION_SOURCE = "eda"  # "eda" | "radlab"
RADLAB_UNIT_CONFIRMED = False

EDA_BASE = "https://visualization.osdr.nasa.gov/eda/api"
RADLAB_URL = "https://visualization.osdr.nasa.gov/radlab/api/"
RADLAB_INSTRUMENT = "DosTel1"
RADLAB_UNIT = "uGy/h"  # from the OSDR docs example; not stated in the API response
TIMEOUT_S = 30.0

# Value keys found by the probe, one table: snapshot field -> (route, key).
SERIES = {
    "temperature_c": ("temperature/iss", "temperature_iss"),  # degC
    "rh_pct": ("humidity/iss", "humidity_iss"),  # % RH
    "co2": ("co2/iss", "co2_iss"),  # ppm (EDA page script: "CO2 [ppm]")
}
CO2_UNIT = "ppm"
RADIATION_ROUTE = "radiation_data"
RADIATION_KEY = "total"  # gcr + saa, mGy/day (EDA page script: "Dose [mGy/day]")
EDA_RADIATION_UNIT = "mGy/day (one value per day, summed)"


@dataclass(frozen=True)
class SeriesSummary:
    n: int
    mean: float
    min: float
    max: float


def _num(v: object) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def summarise_series(values: list[object]) -> SeriesSummary | None:
    nums = [x for x in (_num(v) for v in values) if x is not None]
    if not nums:
        return None
    return SeriesSummary(
        n=len(nums),
        mean=round(sum(nums) / len(nums), 2),
        min=min(nums),
        max=max(nums),
    )


def to_absorbed_mgy(value: float, unit: str) -> float | None:
    """Convert an absorbed-dose total to mGy. Unknown units return None."""
    factors = {"mgy": 1.0, "ugy": 0.001, "µgy": 0.001}
    f = factors.get(unit.strip().lower())
    return None if f is None else round(value * f, 6)


def _d(s: SeriesSummary | None) -> dict[str, Any] | None:
    return None if s is None else asdict(s)


def summarise_cabin(
    temp: list[object], rh: list[object], co2: list[object], *, co2_unit: str
) -> dict[str, Any]:
    cabin: dict[str, Any] = {
        "temperature_c": _d(summarise_series(temp)),
        "rh_pct": _d(summarise_series(rh)),
    }
    co2_s = _d(summarise_series(co2))
    if co2_unit == "mmHg":
        cabin["co2_mmhg"] = co2_s
    else:
        cabin["co2_mmhg"] = None
        cabin["co2_raw"] = co2_s
        cabin["co2_raw_unit"] = co2_unit
    return cabin


async def _get_json(client: httpx.AsyncClient, url: str, urls: list[str], **kw: Any) -> Any:
    r = await client.get(url, timeout=TIMEOUT_S, **kw)
    urls.append(str(r.url))
    r.raise_for_status()
    return r.json()


def _col(rows: list[dict[str, Any]], key: str) -> list[object]:
    return [r.get(key) for r in rows]


async def _radlab_dose(
    client: httpx.AsyncClient, rows: list[dict[str, Any]], urls: list[str]
) -> dict[str, Any]:
    times = sorted(r["time"] for r in rows if r.get("time"))
    lo, hi = (times[0][:16], times[-1][:16]) if times else ("", "")
    # RadLab filters are literal "timestamp>value" query terms, so build the query by hand.
    query = (
        f"instrument_id={RADLAB_INSTRUMENT}&timestamp>{lo}&timestamp<{hi}"
        "&absorbed_dose_rate&format=json"
    )
    body = await _get_json(client, f"{RADLAB_URL}?{query}", urls)
    vals = [row[2] for row in body.get("data", [])]
    summary = summarise_series(vals)
    raw_sum = (
        None if summary is None else round(sum(x for x in map(_num, vals) if x is not None), 6)
    )
    absorbed = None
    if RADLAB_UNIT_CONFIRMED and raw_sum is not None:
        absorbed = to_absorbed_mgy(raw_sum, RADLAB_UNIT)
    return {
        "source": "radlab",
        "absorbed_mgy": absorbed,
        "absorbed_mgy_per_day": None,
        "raw_sum": raw_sum,
        "raw_unit": RADLAB_UNIT,
    }


async def fetch_snapshot(mission: str, *, client: httpx.AsyncClient, now: datetime) -> dict:
    urls: list[str] = []
    missions = await _get_json(client, f"{EDA_BASE}/missions/", urls)
    if mission not in {m.get("name") for m in missions}:
        raise ValueError(f"mission {mission!r} not listed by OSDR EDA")

    series: dict[str, list[dict[str, Any]]] = {}
    for field, (route, _key) in SERIES.items():
        series[field] = await _get_json(client, f"{EDA_BASE}/missions/{mission}/{route}/", urls)
    cabin = summarise_cabin(
        _col(series["temperature_c"], SERIES["temperature_c"][1]),
        _col(series["rh_pct"], SERIES["rh_pct"][1]),
        _col(series["co2"], SERIES["co2"][1]),
        co2_unit=CO2_UNIT,
    )

    dose: dict[str, Any]
    rad_url = f"{EDA_BASE}/missions/{mission}/{RADIATION_ROUTE}/"
    try:
        if RADIATION_SOURCE != "eda":
            raise httpx.HTTPError("radiation source set to radlab")
        rad = await _get_json(client, rad_url, urls)
        vals = _col(rad, RADIATION_KEY)
        nums = [x for x in map(_num, vals) if x is not None]
        if not nums:
            raise httpx.HTTPError("EDA radiation_data is empty")
        raw_sum = round(sum(nums), 5)
        dose = {
            "source": "eda",
            "absorbed_mgy": to_absorbed_mgy(raw_sum, "mGy"),
            "absorbed_mgy_per_day": round(raw_sum / len(nums), 5),
            "raw_sum": raw_sum,
            "raw_unit": EDA_RADIATION_UNIT,
        }
    except httpx.HTTPError:
        dose = await _radlab_dose(client, series["temperature_c"], urls)

    return {
        "fetched_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mission": mission,
        "source_urls": urls,
        "cabin": cabin,
        "dose": dose,
    }


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


async def _run(mission: str) -> dict:
    async with httpx.AsyncClient() as client:
        return await fetch_snapshot(mission, client=client, now=datetime.now(UTC))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch the OSDR EDA cabin and dose snapshot.")
    ap.add_argument("--mission", default=MISSION)
    ap.add_argument("--out", default="data/nasa/osdr_eda_snapshot.json")
    args = ap.parse_args(argv)
    try:
        snap = asyncio.run(_run(args.mission))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"osdr snapshot failed, previous file kept: {exc}", file=sys.stderr)
        return 1
    _write_atomic(Path(args.out), snap)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
