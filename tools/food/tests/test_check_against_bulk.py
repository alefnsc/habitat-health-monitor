import json
from datetime import UTC, datetime
from pathlib import Path

import build_catalog as bc
import check_against_bulk as cab

FIX = Path(__file__).parent / "fixtures"
BULK = FIX / "bulk"


def _catalog() -> dict:
    return bc.build_catalog(
        bc.read_items(FIX / "items_fixture.csv"), bc.BulkSource([BULK]),
        datetime(2026, 11, 14, tzinfo=UTC), generator="g",
    )  # fmt: skip


def test_all_equal(tmp_path, capsys):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(_catalog()))
    assert cab.main(["--catalog", str(p), "--bulk-dir", str(BULK)]) == 0
    assert "all equal" in capsys.readouterr().out


def test_changed_sodium_is_listed(tmp_path, capsys):
    cat = _catalog()
    cat["items"][1]["per100g"]["sodium_mg"] = 999.0
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cat))
    assert cab.main(["--catalog", str(p), "--bulk-dir", str(BULK)]) == 1
    assert "test-drink: sodium_mg" in capsys.readouterr().out
