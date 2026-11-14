"""One-shot scrape of the NASA Human Research Roadmap risk pages (task N10).

Run by hand (`python -m hub.nasa.hrp_scrape --out data/nasa/hrp_risks.json`); the running
hub never calls it. The ratings are programme-level, not personal probabilities.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from hub.contract import INTAKE_INDS

log = logging.getLogger(__name__)

INDEX_URL = "https://humanresearchroadmap.nasa.gov/Risks/"
RISK_URL = "https://humanresearchroadmap.nasa.gov/Risks/risk.aspx"
TIMEOUT_S = 30.0
DELAY_S = 1.0
NOTE = (
    "Ratings are NASA Human System Risk Board programme-level likelihood x consequence "
    "(LxC) values for crew populations. They are not personal probabilities."
)

# Risk ids: Sleep 100, Behavioural 99, Cardiovascular 179, Nutrition 176,
# Medical Conditions 95, Carcinogenesis 96. Consumers map by id, not by title.
INDICATOR_RISKS: dict[str, list[int]] = {
    "sleep_h": [100, 99],
    "mood": [100, 99],
    "hr": [179],
    "bp_sys": [179],
    "bp_dia": [179],
    "glucose": [176],
    "body_temp": [95],
    "space_weather": [96],
    "rad_dose_cum": [96],
    **{ind: [176] for ind in sorted(INTAKE_INDS)},
    "body_mass": [176],
}


@dataclass
class RiskRef:
    id: int
    title: str
    active: bool


@dataclass
class Rating:
    mission_category: str
    duration: str
    operations_lxc: str
    operations_disposition: str
    long_term_lxc: str
    long_term_disposition: str


@dataclass
class Risk:
    id: int
    title: str
    risk_statement: str | None
    last_published: str | None
    board_approved: str | None
    source_url: str
    ratings: list[Rating] = field(default_factory=list)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_index(html: str) -> list[RiskRef]:
    soup = BeautifulSoup(html, "html.parser")
    refs = []
    for a in soup.select("a.relatedItemLink"):
        m = re.search(r"i=(\d+)", a.get("href", ""))
        if not m:
            continue
        title = _clean(a.get_text())
        inactive = title.endswith("[inactive]")
        refs.append(
            RiskRef(int(m.group(1)), title.removesuffix("[inactive]").strip(), not inactive)
        )
    return refs


def _cell(row, suffix: str) -> str:
    td = row.find("td", id=lambda i: bool(i) and i.endswith(suffix))
    return _clean(td.get_text()) if td else ""


def parse_risk(html: str, risk_id: int, url: str) -> Risk:
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text()) if soup.title else ""
    title = title.removeprefix("HRR - Risk - ")

    lp = soup.find(id="ctl00_content_ltlLastPublished")
    m = re.match(r"\d{2}/\d{2}/\d{2}", _clean(lp.get_text())) if lp else None
    last_published = m.group(0) if m else None

    footer = soup.find(id="ctl00_content_lblRatingFooterPrefix")
    foot_text = _clean(footer.parent.get_text()) if footer and footer.parent else ""
    m = re.search(r"last approved by the Human System Risk Board in (\d{1,2}/\d{4})", foot_text)
    board_approved = m.group(1) if m else None

    statement = None
    head = soup.find(id="ctl00_content_divRiskStatement")
    body = head.find_next_sibling("div") if head else None
    if body:
        text = _clean(body.get_text())
        # Some pages carry the LxC footnote in this slot; it is not a risk statement.
        statement = None if text.startswith("LxC is") else text

    ratings: list[Rating] = []
    category = ""
    for row in soup.select("tr[id^=ctl00_content_tr]"):
        cat = row.find("td", class_="riskRatingCategory")
        if cat:
            category = _clean(cat.get_text())
        plain = [td for td in row.find_all("td") if not td.get("id") and td is not cat]
        ratings.append(
            Rating(
                mission_category=category,
                duration=_clean(plain[0].get_text(" ")) if plain else "",
                operations_lxc=_cell(row, "OpsLxC"),
                operations_disposition=_cell(row, "OpsDisposition"),
                long_term_lxc=_cell(row, "LTHLxC"),
                long_term_disposition=_cell(row, "LTHDisposition"),
            )
        )
    return Risk(risk_id, title, statement, last_published, board_approved, url, ratings)


async def scrape(client: httpx.AsyncClient, *, now: datetime, delay_s: float = DELAY_S) -> dict:
    r = await client.get(INDEX_URL, timeout=TIMEOUT_S)
    r.raise_for_status()
    refs = [x for x in parse_index(r.text) if x.active]
    risks: list[Risk] = []
    for n, ref in enumerate(refs):
        if n and delay_s:
            await asyncio.sleep(delay_s)
        url = f"{RISK_URL}?i={ref.id}"
        try:
            page = await client.get(url, timeout=TIMEOUT_S)
            page.raise_for_status()
            risk = parse_risk(page.text, ref.id, url)
            risk.title = risk.title or ref.title
        except Exception as exc:  # noqa: BLE001 - one bad page must not abort the run
            log.warning("risk %s failed: %s", ref.id, exc)
            risk = Risk(ref.id, ref.title, None, None, None, url, [])
        risks.append(risk)
    return {
        "scraped_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": INDEX_URL,
        "note": NOTE,
        "risks": [asdict(x) for x in risks],
        "indicator_map": INDICATOR_RISKS,
    }


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


async def _run() -> dict:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        return await scrape(client, now=datetime.now(UTC))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape HRP risk pages once.")
    ap.add_argument("--out", default="data/nasa/hrp_risks.json")
    args = ap.parse_args(argv)
    try:
        data = asyncio.run(_run())
    except httpx.HTTPError as exc:
        print(f"HRP scrape failed, previous file kept: {exc}", file=sys.stderr)
        return 1
    _write_atomic(Path(args.out), data)
    print(f"wrote {args.out} ({len(data['risks'])} risks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
