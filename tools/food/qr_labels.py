"""Printable QR labels for the habitat's food packs (D44).

Each label holds the QR text `hhm-food:<item-id>` and prints the same code under it, so the console's pack scanner
or a typed code picks that catalogue food. Needs the optional `labels` extra (segno, BSD-3-Clause).

    python tools/food/qr_labels.py --catalog data/food/catalog.json --out var/food-labels.html
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path

import segno

PREFIX = "hhm-food:"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Food pack labels</title>
<style>
body {{ font: 12px/1.3 system-ui, sans-serif; margin: 12mm; }}
.sheet {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 6mm; }}
.label {{ border: 1px dashed #888; padding: 3mm; text-align: center; break-inside: avoid; }}
.code {{ font-family: ui-monospace, monospace; }}
</style></head><body>
<p>Food pack labels: QR text is the pack code printed under it. Generic foods, sample data.</p>
<div class="sheet">
{labels}
</div></body></html>
"""


def pack_code(item_id: str) -> str:
    return PREFIX + item_id


def label_sheet(catalog: Mapping) -> str:
    labels = []
    for it in catalog["items"]:
        code = pack_code(it["id"])
        qr = segno.make_qr(code, error="m").svg_inline(scale=4)
        labels.append(
            f'<div class="label">{qr}<div><strong>{escape(it["name"])}</strong></div>'
            f'<div>{escape(it["serving_label"])}</div><div class="code">{escape(code)}</div></div>'
        )
    return PAGE.format(labels="\n".join(labels))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    cat = json.loads(a.catalog.read_text(encoding="utf-8"))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(label_sheet(cat), encoding="utf-8")
    print(f"wrote {len(cat['items'])} labels to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
