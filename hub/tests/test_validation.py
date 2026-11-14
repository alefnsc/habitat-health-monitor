"""S6a tests. Synthetic fixtures only: no real person's data."""

from datetime import UTC, datetime, timedelta

import pytest

from hub import validation as v


def rd(ind, val, ts, *, src="hobby", dev="MAX30102", q=("ok",), crew="crew-a", unit="bpm"):
    return {"ind": ind, "val": val, "measured_at": ts, "src": src, "dev": dev,
            "q": list(q), "crew": crew, "unit": unit}  # fmt: skip


REF = rd("hr", 72, "2026-11-14T15:20:30.000Z", src="certified", dev="manual")


def test_bland_altman_values():
    ba = v.bland_altman([72, 75, 80, 90], [70, 76, 78, 88])
    assert ba["n"] == 4
    assert round(ba["bias"], 2) == 1.25 and round(ba["sd"], 2) == 1.5
    assert round(ba["loa_low"], 2) == -1.69 and round(ba["loa_high"], 2) == 4.19
    assert round(ba["arms"], 2) == 1.80


def test_bland_altman_too_few():
    with pytest.raises(ValueError, match="need at least 2 pairs"):
        v.bland_altman([1], [1])


def test_pair_median_window():
    rows = [REF, rd("hr", 70, "2026-11-14T15:20:22Z"), rd("hr", 74, "2026-11-14T15:20:25Z"),
            rd("hr", 90, "2026-11-14T15:20:28Z", q=["motion"])]  # fmt: skip
    pairs, fails = v.pair_readings(rows, "hr", "hr", "MAX30102", 10)
    assert fails == [] and len(pairs) == 1
    assert pairs[0]["test_val"] == 72.0 and pairs[0]["ref_val"] == 72


def test_window_cap():
    with pytest.raises(ValueError, match=r"window_s must be ≤ 60"):
        v.pair_readings([], "hr", "hr", "MAX30102", 90)


def test_pair_no_test_reading():
    ref = rd("hr", 70, "2026-11-14T15:30:00Z", src="certified", dev="manual")
    pairs, fails = v.pair_readings([ref], "hr", "hr", "MAX30102", 10)
    assert pairs == [] and [f["reason"] for f in fails] == ["no_test_reading"]


def test_pair_all_flagged():
    rows = [REF, rd("hr", 80, "2026-11-14T15:20:25Z", q=["no_contact"])]
    pairs, fails = v.pair_readings(rows, "hr", "hr", "MAX30102", 10)
    assert pairs == [] and [f["reason"] for f in fails] == ["flagged_no_contact"]


def test_pair_filters_dev():
    ref = rd("body_temp", 36.6, "2026-11-14T15:20:30Z", src="certified", dev="manual", unit="C")
    rows = [ref, rd("skin_temp", 34.0, "2026-11-14T15:20:20Z", dev="DS18B20", unit="C"),
            rd("skin_temp", 35.0, "2026-11-14T15:20:25Z", dev="MLX90614", unit="C")]  # fmt: skip
    pairs, _ = v.pair_readings(rows, "body_temp", "skin_temp", "MLX90614", 30)
    assert pairs[0]["test_val"] == 35.0


def test_pair_subject():
    ref = rd("hr", 72, "2026-11-14T15:20:30Z", src="certified", dev="manual", crew="crew-b")
    rows = [ref, rd("hr", 99, "2026-11-14T15:20:25Z", crew="crew-a"),
            rd("hr", 71, "2026-11-14T15:20:27Z", crew=None)]  # fmt: skip
    pairs, fails = v.pair_readings(rows, "hr", "hr", "MAX30102", 10)
    assert fails == [] and pairs[0]["test_val"] == 71.0 and pairs[0]["subject"] == "crew-b"


def _twenty_pairs():
    t0 = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)
    rows = []
    for i in range(20):
        t = t0 + timedelta(seconds=40 * i)
        iso = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(rd("hr", 60 + i, iso, src="certified", dev="manual"))
        rows.append(
            rd(
                "hr",
                60 + i + (i % 3) - 1,
                (t - timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return rows


def test_plot_writes_png(tmp_path):
    pytest.importorskip("matplotlib")  # needs the [analysis] extra (D15)
    pairs, _ = v.pair_readings(_twenty_pairs(), "hr", "hr", "MAX30102", 10)
    assert len(pairs) == 20
    out = str(tmp_path / "ba.png")
    assert v.plot_bland_altman(pairs, "HR", "bpm", out) == out
    assert (tmp_path / "ba.png").stat().st_size > 0


def test_summary_row_format():
    ba = v.bland_altman([72, 75, 80, 90], [70, 76, 78, 88])
    row = v.summary_row("MAX30102 hr vs oximeter", "bpm", ba, 6, [{}, {}])
    assert row == "| MAX30102 hr vs oximeter | 4 | 2 | +1.25 bpm | 1.50 | −1.69 to +4.19 bpm |"


def test_vitals_cli_stub_hub(tmp_path, monkeypatch, capsys):
    pytest.importorskip("matplotlib")  # needs the [analysis] extra (D15)
    rows = _twenty_pairs()
    monkeypatch.setattr(v, "_fetch", lambda hub, ind, since: [r for r in rows if r["ind"] == ind])
    out, img = tmp_path / "out", tmp_path / "img"
    code = v.main(["vitals", "--hub", "http://hub", "--since", "2026-11-14T00:00:00Z",
                   "--out", str(out), "--img", str(img)])  # fmt: skip
    assert code == 0
    assert (out / "pairs-2026-11-14.csv").exists() and (out / "failures-2026-11-14.csv").exists()
    assert (img / "validation-hr.png").exists()
    assert not (img / "validation-mlx90614.png").exists()
    printed = capsys.readouterr().out
    assert "MLX90614 skin_temp vs thermometer | 0 | 0 | n below target (0)" in printed
