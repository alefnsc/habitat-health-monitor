"""Diff data/food/catalog.json against the FDC bulk CSV files.

Exit 0 and print "all equal" when every nutrient of every item matches the bulk value.
Exit 1 and list each difference (item id, nutrient) otherwise.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from build_catalog import PER100G_IDS, BulkSource, energy_kcal


def diff_catalog(catalog: dict, source: BulkSource) -> list[str]:
    problems: list[str] = []
    for item in catalog["items"]:
        iid, fdc = item["id"], item["fdc_id"]
        try:
            nutrients = source.get(fdc)
        except KeyError:
            problems.append(f"{iid}: FDC id {fdc} not in the bulk files")
            continue
        kcal, basis = energy_kcal(nutrients)
        expected = {
            k: (None if nutrients.get(nid) is None else float(nutrients[nid]))
            for k, nid in PER100G_IDS.items()
        }
        expected["kcal"] = kcal
        for key, want in expected.items():
            got = item["per100g"].get(key)
            if got != want:
                problems.append(f"{iid}: {key} catalogue {got!r} bulk {want!r}")
        if item["kcal_basis"] != basis:
            problems.append(f"{iid}: kcal_basis catalogue {item['kcal_basis']} bulk {basis}")
        if item["fdc_description"] != source.meta(fdc)["description"]:
            problems.append(f"{iid}: fdc_description differs")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--bulk-dir", required=True, action="append", type=Path)
    args = ap.parse_args(argv)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    problems = diff_catalog(catalog, BulkSource(args.bulk_dir))
    if problems:
        print("\n".join(problems))
        return 1
    print(f"all equal ({len(catalog['items'])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
