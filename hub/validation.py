"""Validation analysis (S6a): pair reference and test readings, Bland-Altman, charts.

Reference readings are certified manual entries (src "certified"). Test readings come from a
hobby sensor (dev e.g. MAX30102). Pairing follows docs/drafts/s5-validation-protocol.md:
t is the reference measured_at, the test value is the median of `ok` test readings in
[t - window_s, t], and crew must match when both sides have one (D11, window capped at 60 s).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_WINDOW_S = 60
TARGET_N = 20
MINUS = "−"


def _parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def pair_readings(
    readings: list[dict], ref_ind: str, test_ind: str, test_dev: str, window_s: int
) -> tuple[list[dict], list[dict]]:
    """Return (pairs, failures). A pair holds subject, t, ref_val, test_val, n_test, unit."""
    if window_s > MAX_WINDOW_S:
        raise ValueError(f"window_s must be ≤ {MAX_WINDOW_S}")
    refs = [r for r in readings if r["ind"] == ref_ind and r.get("src") == "certified"]
    tests = [
        r
        for r in readings
        if r["ind"] == test_ind and r.get("dev") == test_dev and r.get("src") != "certified"
    ]
    pairs: list[dict] = []
    failures: list[dict] = []
    for ref in sorted(refs, key=lambda r: r["measured_at"]):
        t = _parse_ts(ref["measured_at"])
        lo = t - timedelta(seconds=window_s)
        crew = ref.get("crew")
        in_window = [
            r
            for r in tests
            if lo <= _parse_ts(r["measured_at"]) <= t
            and (crew is None or r.get("crew") is None or r["crew"] == crew)
        ]
        good = [r for r in in_window if list(r.get("q") or []) == ["ok"]]
        if not in_window:
            failures.append({"t": ref["measured_at"], "subject": crew, "reason": "no_test_reading"})
        elif not good:
            flag = next((f for r in in_window for f in r.get("q", []) if f != "ok"), "unknown")
            failures.append({"t": ref["measured_at"], "subject": crew, "reason": f"flagged_{flag}"})
        else:
            pairs.append(
                {
                    "subject": crew,
                    "t": ref["measured_at"],
                    "ref_val": ref["val"],
                    "test_val": float(statistics.median(r["val"] for r in good)),
                    "n_test": len(good),
                    "unit": ref.get("unit"),
                }
            )
    return pairs, failures


def bland_altman(test: list[float], ref: list[float]) -> dict:
    if len(test) != len(ref):
        raise ValueError("test and ref must have the same length")
    if len(test) < 2:
        raise ValueError("need at least 2 pairs")
    d = [a - b for a, b in zip(test, ref, strict=True)]
    bias = statistics.fmean(d)
    sd = statistics.stdev(d)
    return {
        "n": len(d),
        "bias": bias,
        "sd": sd,
        "loa_low": bias - 1.96 * sd,
        "loa_high": bias + 1.96 * sd,
        "arms": math.sqrt(statistics.fmean(x * x for x in d)),
    }


def plot_bland_altman(pairs: list[dict], title: str, unit: str, out_path: str) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    test = [p["test_val"] for p in pairs]
    ref = [p["ref_val"] for p in pairs]
    ba = bland_altman(test, ref)
    mean = [(a + b) / 2 for a, b in zip(test, ref, strict=True)]
    diff = [a - b for a, b in zip(test, ref, strict=True)]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(mean, diff, s=18)
    ax.axhline(ba["bias"], color="tab:blue", label=f"bias {ba['bias']:+.2f}")
    ax.axhline(
        ba["loa_high"], color="tab:red", linestyle="--", label=f"+1.96 SD {ba['loa_high']:+.2f}"
    )
    ax.axhline(
        ba["loa_low"], color="tab:red", linestyle="--", label=f"-1.96 SD {ba['loa_low']:+.2f}"
    )
    ax.set_xlabel(f"Mean of test and reference ({unit})")
    ax.set_ylabel(f"Test - reference ({unit})")
    ax.set_title(f"{title} (n = {ba['n']})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", dpi=150)
    plt.close(fig)
    return out_path


def _signed(x: float) -> str:
    return f"{x:+.2f}".replace("-", MINUS)


def summary_row(
    label: str, unit: str, ba: dict | None, n_attempted: int, failures: list[dict]
) -> str:
    n_valid = ba["n"] if ba else n_attempted - len(failures)
    if ba is None:
        return f"| {label} | {n_valid} | {len(failures)} | n below target ({n_valid}) |"
    return (
        f"| {label} | {ba['n']} | {len(failures)} | {_signed(ba['bias'])} {unit} | {ba['sd']:.2f} | "
        f"{_signed(ba['loa_low'])} to {_signed(ba['loa_high'])} {unit} |"
    )


WORK_X_LABEL = "Cell work (J), approx.: static cell force \u00d7 camera displacement"


def pair_reps(aligned: dict) -> tuple[list[dict], list[dict]]:
    """Pair camera and load-cell reps from one `GET /api/reps?session=` body (D5, D21)."""
    session = aligned.get("session")
    pairs: list[dict] = []
    failures: list[dict] = []
    for rp in aligned.get("pairs", []):
        cam, cell = rp.get("camera"), rp.get("load_cell")
        if cam is None:
            failures.append(
                {"session": session, "rep": rp["rep"], "reason": "unmatched_load_cell_rep"}
            )
        elif cell is None:
            failures.append(
                {"session": session, "rep": rp["rep"], "reason": "unmatched_camera_rep"}
            )
        else:
            pairs.append(
                {
                    "session": session,
                    "rep": rp["rep"],
                    "camera_peak_n": cam["peak_n"],
                    "load_cell_peak_n": cell["peak_n"],
                    "camera_work_j": cam.get("work_j"),
                    "work_cell_j": rp.get("work_cell_j"),
                    "mass_kg": cam.get("mass_kg", cell.get("mass_kg")),
                }
            )
    return pairs, failures


def _plot_xy(x, y, xlabel, ylabel, title, out_path, colour=None, colour_label=None) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    sc = ax.scatter(x, y, c=colour, s=22, cmap="viridis" if colour is not None else None)
    lo, hi = min([*x, *y]), max([*x, *y])
    ax.plot([lo, hi], [lo, hi], color="grey", linestyle=":", label="y = x")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if colour is not None:
        fig.colorbar(sc, ax=ax, label=colour_label)
    ax.legend(fontsize=8)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", dpi=150)
    plt.close(fig)
    return out_path


def _fetch_reps(hub: str, session: str) -> dict:
    q = urllib.parse.urlencode({"session": session})
    with urllib.request.urlopen(f"{hub.rstrip('/')}/api/reps?{q}", timeout=30) as r:
        return json.loads(r.read())


def _share(k: int, n: int) -> str:
    return f"{k}/{n} = {100 * k / n:.0f} %" if n else "n/a"


def tilt_rows(bodies: list[dict]) -> list[str]:
    """D39: how often the tilt switch witnessed a camera rep, and how far its midpoint sat
    from the camera turnaround."""
    # A camera rep with no tilt result (no t_turn_ms) cannot be witnessed, so it is not counted.
    cams = [p for b in bodies for p in b.get("pairs", []) if p.get("camera") and p.get("tilt") is not None]
    seen = [p["tilt"] for p in cams if p.get("tilt") and p["tilt"].get("seen")]
    inside = [t for t in seen if t.get("turn_inside")]
    offs = sorted(abs(t["offset_ms"]) for t in seen)
    if offs:
        p95 = offs[math.ceil(0.95 * len(offs)) - 1]
        spread = f"{statistics.median(offs):.0f} ms / {p95:.0f} ms"
    else:
        spread = "n/a"
    return [
        f"| Tilt witness seen | {_share(len(seen), len(cams))} |",
        f"| Turnaround inside tilt interval | {_share(len(inside), len(seen))} |",
        f"| Tilt offset, abs median / p95 | {spread} |",
    ]


def run_reps(hub: str, sessions: list[str], out: str, img: str) -> list[str]:
    out_dir, img_dir = Path(out), Path(img)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_pairs: list[dict] = []
    all_fail: list[dict] = []
    n_cam = n_cell = 0
    cols = [
        "session",
        "rep",
        "camera_peak_n",
        "load_cell_peak_n",
        "camera_work_j",
        "work_cell_j",
        "mass_kg",
    ]
    bodies: list[dict] = []
    for sid in sessions:
        body = _fetch_reps(hub, sid)
        bodies.append(body)
        pairs, fails = pair_reps(body)
        _write_csv(out_dir / f"reps-{sid}.csv", pairs, cols)
        all_pairs += pairs
        all_fail += fails
        n_cam += sum(1 for p in body.get("pairs", []) if p.get("camera"))
        n_cell += sum(1 for p in body.get("pairs", []) if p.get("load_cell"))
    rows: list[str] = []
    ba = None
    if len(all_pairs) >= 2:
        cam = [p["camera_peak_n"] for p in all_pairs]
        cell = [p["load_cell_peak_n"] for p in all_pairs]
        ba = bland_altman(cam, cell)
        _plot_xy(cell, cam, "Load cell peak force (N)", "Camera peak force (N)",
                 f"Peak force, camera vs load cell (n = {ba['n']})",
                 str(img_dir / "validation-peak-force.png"),
                 colour=[p["mass_kg"] for p in all_pairs], colour_label="Load mass (kg)")  # fmt: skip
    rows.append(
        summary_row(
            "Peak force, camera vs load cell", "N", ba, len(all_pairs) + len(all_fail), all_fail
        )
    )
    wp = [p for p in all_pairs if p["camera_work_j"] is not None and p["work_cell_j"] is not None]
    wba = None
    if len(wp) >= 2:
        wba = bland_altman([p["camera_work_j"] for p in wp], [p["work_cell_j"] for p in wp])
        _plot_xy([p["work_cell_j"] for p in wp], [p["camera_work_j"] for p in wp], WORK_X_LABEL,
                 "Camera work (J)", f"Work, camera vs cell, approximation (n = {wba['n']})",
                 str(img_dir / "validation-work.png"))  # fmt: skip
    rows.append(summary_row("Work, camera vs cell (approx., report only)", "J", wba, len(wp), []))
    denom = max(n_cam, n_cell)
    agree = f"{len(all_pairs)}/{denom} = {100 * len(all_pairs) / denom:.0f} %" if denom else "n/a"
    rows.append(f"| Rep detection agreement | {agree} |")
    rows += tilt_rows(bodies)
    return rows


COMPARISONS = [
    # slug, label, ref_ind, test_ind, test_dev, window_s, unit
    ("hr", "MAX30102 hr vs oximeter", "hr", "hr", "MAX30102", 10, "bpm"),
    ("spo2", "MAX30102 spo2 vs oximeter", "spo2", "spo2", "MAX30102", 10, "%"),
    ("ds18b20", "DS18B20 skin_temp vs thermometer", "body_temp", "skin_temp", "DS18B20", 30, "C"),
    (
        "mlx90614",
        "MLX90614 skin_temp vs thermometer",
        "body_temp",
        "skin_temp",
        "MLX90614",
        30,
        "C",
    ),
]


def _fetch(hub: str, ind: str, since: str) -> list[dict]:
    q = urllib.parse.urlencode({"ind": ind, "since": since, "limit": 5000})
    with urllib.request.urlopen(f"{hub.rstrip('/')}/api/readings?{q}", timeout=30) as r:
        return json.loads(r.read())


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run_vitals(hub: str, since: str, until: str | None, out: str, img: str) -> list[str]:
    out_dir, img_dir = Path(out), Path(img)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, list[dict]] = {}
    until_dt = _parse_ts(until) if until else None
    all_pairs: list[dict] = []
    all_failures: list[dict] = []
    rows: list[str] = []
    for slug, label, ref_ind, test_ind, dev, win, unit in COMPARISONS:
        readings: list[dict] = []
        for ind in {ref_ind, test_ind}:
            if ind not in cache:
                cache[ind] = _fetch(hub, ind, since)
            readings += cache[ind]
        if until_dt:
            readings = [r for r in readings if _parse_ts(r["measured_at"]) <= until_dt]
        pairs, failures = pair_readings(readings, ref_ind, test_ind, dev, win)
        for p in pairs:
            all_pairs.append({**p, "comparison": slug})
        for f in failures:
            all_failures.append({**f, "comparison": slug})
        ba = None
        if len(pairs) >= 2:
            ba = bland_altman([p["test_val"] for p in pairs], [p["ref_val"] for p in pairs])
            plot_bland_altman(pairs, label, unit, str(img_dir / f"validation-{slug}.png"))
        rows.append(summary_row(label, unit, ba, len(pairs) + len(failures), failures))
    date = since[:10]
    _write_csv(
        out_dir / f"pairs-{date}.csv",
        all_pairs,
        ["comparison", "subject", "t", "ref_val", "test_val", "n_test", "unit"],
    )
    _write_csv(
        out_dir / f"failures-{date}.csv", all_failures, ["comparison", "subject", "t", "reason"]
    )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hub.validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("vitals")
    v.add_argument("--hub", required=True)
    v.add_argument("--since", required=True)
    v.add_argument("--until")
    v.add_argument("--out", default="data/validation/")
    v.add_argument("--img", default="docs/img/")
    r = sub.add_parser("reps")
    r.add_argument("--hub", required=True)
    r.add_argument("--session", action="append", required=True)
    r.add_argument("--out", default="data/validation/")
    r.add_argument("--img", default="docs/img/")
    a = ap.parse_args(argv)
    if a.cmd == "reps":
        for row in run_reps(a.hub, a.session, a.out, a.img):
            print(row)
        return 0
    print("| Comparison | n | failed | bias | SD | limits of agreement |")
    for row in run_vitals(a.hub, a.since, a.until, a.out, a.img):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
