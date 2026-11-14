"""D39 tilt rows in the reps validation report. Synthetic bodies only."""

from hub import validation as v


def body(tilts):
    pairs = [{"rep": i + 1, "camera": {"peak_n": 120.0, "work_j": 30.0, "mass_kg": 10},
              "load_cell": None, "work_cell_j": None, "tilt": t} for i, t in enumerate(tilts)]  # fmt: skip
    return {"session": "s1", "pairs": pairs}


def w(offset, inside=True):
    return {"seen": True, "turn_inside": inside, "offset_ms": offset, "rise_at": "x", "fall_at": "y"}


NOT_SEEN = {"seen": False, "turn_inside": False, "offset_ms": None, "rise_at": None, "fall_at": None}


def test_tilt_rows_counts_and_percentiles():
    rows = v.tilt_rows([body([w(40), w(-60), w(100, inside=False), NOT_SEEN, None])])
    assert rows == [
        "| Tilt witness seen | 3/4 = 75 % |",
        "| Turnaround inside tilt interval | 2/3 = 67 % |",
        "| Tilt offset, abs median / p95 | 60 ms / 100 ms |",
    ]


def test_tilt_rows_without_witnesses():
    rows = v.tilt_rows([body([None, NOT_SEEN])])
    assert rows == [
        "| Tilt witness seen | 0/1 = 0 % |",
        "| Turnaround inside tilt interval | n/a |",
        "| Tilt offset, abs median / p95 | n/a |",
    ]
    assert v.tilt_rows([]) == [
        "| Tilt witness seen | n/a |",
        "| Turnaround inside tilt interval | n/a |",
        "| Tilt offset, abs median / p95 | n/a |",
    ]


def test_reps_cli_prints_tilt_rows(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(v, "_fetch_reps", lambda hub, sid: body([w(10), w(20)]))
    code = v.main(["reps", "--hub", "http://hub", "--session", "s1",
                   "--out", str(tmp_path / "o"), "--img", str(tmp_path / "i")])  # fmt: skip
    assert code == 0
    assert "| Tilt witness seen | 2/2 = 100 % |" in capsys.readouterr().out
