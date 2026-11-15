"""Printable pack labels (D44): one QR code per catalogue item, text `hhm-food:<item-id>`."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("segno")  # optional `labels` extra; the shared venv may not have it

import qr_labels as ql

CAT = {
    "items": [
        {"id": "bar", "name": "Test bar <one>", "serving_label": "1 bar (40 g)"},
        {"id": "drink", "name": "Test drink", "serving_label": "1 cup"},
    ]
}


def test_one_label_per_item_with_its_code():
    html = ql.label_sheet(CAT)
    assert html.count("<svg") == 2
    assert "hhm-food:bar" in html and "hhm-food:drink" in html


def test_names_are_escaped():
    html = ql.label_sheet(CAT)
    assert "Test bar &lt;one&gt;" in html
    assert "<one>" not in html


def test_sheet_loads_nothing_from_the_network():
    assert not re.search(r"(src|href)=\"https?://", ql.label_sheet(CAT))


def test_qr_holds_the_pack_code():
    # segno's own decoder is not available, so compare against segno's encoding of the same text.
    import segno

    want = segno.make_qr("hhm-food:bar", error="m").svg_inline(scale=4)
    assert want in ql.label_sheet(CAT)


def test_cli_writes_the_sheet(tmp_path: Path):
    cat = tmp_path / "catalog.json"
    cat.write_text(json.dumps(CAT), encoding="utf-8")
    out = tmp_path / "labels.html"
    assert ql.main(["--catalog", str(cat), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").count("<svg") == 2
