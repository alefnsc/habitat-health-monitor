"""S6b tests. Synthetic fixtures only."""

from hub import validation as v


def rep(peak, work, mass=10.0):
    return {"peak_n": peak, "work_j": work, "mass_kg": mass}


def session(sid, n=8, drop_cell=None, drop_cam=None, work_cell=True):
    pairs = []
    for i in range(1, n + 1):
        pairs.append({
            "rep": i,
            "camera": None if i == drop_cam else rep(120.0 + i, 30.0 + i),
            "load_cell": None if i == drop_cell else rep(118.0 + i, None),
            "work_cell_j": (29.0 + i) if work_cell else None,
        })  # fmt: skip
    return {"session": sid, "pairs": pairs}


def test_pair_reps_unmatched_camera():
    pairs, fails = v.pair_reps(session("s1", drop_cell=8))
    assert len(pairs) == 7
    assert [f["reason"] for f in fails] == ["unmatched_camera_rep"]


def test_pair_reps_unmatched_cell():
    pairs, fails = v.pair_reps(session("s1", drop_cam=3))
    assert len(pairs) == 7 and [f["reason"] for f in fails] == ["unmatched_load_cell_rep"]


def test_pair_reps_work_missing():
    body = session("s1", n=3)
    body["pairs"][1]["work_cell_j"] = None
    pairs, fails = v.pair_reps(body)
    assert fails == [] and len(pairs) == 3 and pairs[1]["work_cell_j"] is None


def test_pair_reps_values():
    body = {"session": "s1", "pairs": [{"rep": 1, "camera": rep(120.0, 30.0),
                                        "load_cell": rep(118.0, None), "work_cell_j": 29.0}]}  # fmt: skip
    (p,), _ = v.pair_reps(body)
    assert (p["camera_peak_n"], p["load_cell_peak_n"], p["camera_work_j"], p["work_cell_j"]) == (
        120.0, 118.0, 30.0, 29.0)  # fmt: skip
    assert p["session"] == "s1" and p["rep"] == 1 and p["mass_kg"] == 10.0


def test_reps_cli_multi_session(tmp_path, monkeypatch, capsys):
    data = {"s1": session("s1"), "s2": session("s2")}
    monkeypatch.setattr(v, "_fetch_reps", lambda hub, sid: data[sid])
    out, img = tmp_path / "o", tmp_path / "i"
    code = v.main(["reps", "--hub", "http://hub", "--session", "s1", "--session", "s2",
                   "--out", str(out), "--img", str(img)])  # fmt: skip
    assert code == 0
    assert (out / "reps-s1.csv").exists() and (out / "reps-s2.csv").exists()
    assert (img / "validation-peak-force.png").exists() and (img / "validation-work.png").exists()
    printed = capsys.readouterr().out
    assert "| Peak force, camera vs load cell | 16 |" in printed
    assert "Rep detection agreement | 16/16 = 100 %" in printed


def test_work_axis_label():
    assert "static cell force" in v.WORK_X_LABEL and "camera displacement" in v.WORK_X_LABEL
    assert "mean" not in v.WORK_X_LABEL.lower()
