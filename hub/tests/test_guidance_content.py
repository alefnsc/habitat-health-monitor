"""S12: content tests for data/guidance.json against the rules and docs/guidance-review.md."""

import json
import re
from pathlib import Path

from hub.contract import DERIVED, INDICATORS

ROOT = Path(__file__).resolve().parents[2]
ITEMS = json.loads((ROOT / "data" / "guidance.json").read_text(encoding="utf-8"))
BY_ID = {i["id"]: i for i in ITEMS}
FORBIDDEN = ["diagnos", "you have", "hypertension", "hypotension", "fever", "infection", "disease",
             "disorder", "depress", "tablet", "pill", "capsule", "dose of", "milligram", "mg "]  # fmt: skip


def _rules():
    return json.loads((ROOT / "data" / "thresholds.json").read_text(encoding="utf-8"))


def _texts(item):
    return [item.get(k, "") for k in ("do_now", "tell", "why")]


def test_ids_unique():
    assert len(BY_ID) == len(ITEMS)


def test_every_rule_status_has_text():
    for r in _rules():
        for status in ("watch", "act"):
            if r.get(status) is not None:
                assert f"{r['id']}.{status}" in BY_ID, f"{r['id']}.{status}"
    for gid in ("baseline_2sd.watch", "default.ok", "default.unknown"):
        assert gid in BY_ID


def test_escalation_values():
    for i in ITEMS:
        assert i["escalate_to"] in {"self", "cmo", "flight_surgeon"}, i["id"]
        if i["status"] == "act":
            assert i["escalate_to"] in {"cmo", "flight_surgeon"}, i["id"]
    assert BY_ID["radiation_spe.act"]["escalate_to"] == "flight_surgeon"
    assert BY_ID["radiation_career.act"]["escalate_to"] == "flight_surgeon"


def test_food_escalation():
    for i in ITEMS:
        if i["rule_id"].startswith("intake_"):
            assert i["escalate_to"] == ("self" if i["status"] == "watch" else "cmo"), i["id"]


def test_no_diagnosis_or_dose():
    for i in ITEMS:
        for text in _texts(i):
            low = text.lower()
            for w in FORBIDDEN:
                assert w not in low, f"{i['id']}: {w!r}"


def test_risk_links():
    ok = (
        "https://humanresearchroadmap.nasa.gov/",
        "https://www.nasa.gov/",
        "https://standards.nasa.gov/",
    )
    for i in ITEMS:
        assert not i["risk_url"] or i["risk_url"].startswith(ok), i["id"]


def test_risk_ids_exist():
    risks = json.loads((ROOT / "data" / "nasa" / "hrp_risks.json").read_text(encoding="utf-8"))
    known = {r["id"] for r in risks["risks"]}
    for i in ITEMS:
        m = re.search(r"\?i=(\d+)$", i["risk_url"])
        if m:
            assert int(m.group(1)) in known, i["id"]


def test_length():
    for i in ITEMS:
        for text in _texts(i):
            assert len(text) <= 160, f"{i['id']}: {len(text)}"


def test_matches_review():
    review = (ROOT / "docs" / "guidance-review.md").read_text(encoding="utf-8")
    for i in ITEMS:
        for text in _texts(i):
            assert text in review, f"{i['id']}: text not in review"


def test_why_field():
    for ind in ("hr", "bp_sys", "bp_dia", "glucose", "body_temp", "sleep_h", "mood"):
        e = BY_ID[f"default.{ind}"]
        assert e["why"].strip() and e["risk_url"].strip() and e["status"] == "info"
    assert BY_ID["default.bp_dia"]["why"] == BY_ID["default.bp_sys"]["why"]


def test_indicators_known_in_text_ids():
    for i in ITEMS:
        if i["rule_id"] == "default" and i["status"] == "info":
            assert i["id"].split(".", 1)[1] in INDICATORS or i["id"].split(".", 1)[1] in DERIVED
