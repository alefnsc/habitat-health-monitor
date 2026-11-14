from datetime import UTC, datetime
from pathlib import Path

from hub.nasa.spaceweather import evaluate_space_weather, load_replay, parse_donki_time

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
REPLAY = Path(__file__).resolve().parents[2] / "data" / "nasa" / "donki_replay_2025-11.json"


def ev(flr=None, sep=None, gst=None):
    return evaluate_space_weather({"FLR": flr or [], "SEP": sep or [], "GST": gst or []}, NOW)


def test_parse_donki_time_without_seconds():
    assert parse_donki_time("2025-11-10T22:30Z") == datetime(2025, 11, 10, 22, 30, tzinfo=UTC)
    assert parse_donki_time("2025-11-10T22:30:15Z") == datetime(
        2025, 11, 10, 22, 30, 15, tzinfo=UTC
    )


def test_sep_within_24h_is_act():
    a = ev(sep=[{"sepID": "2026-11-14T10:00:00-SEP-001", "eventTime": "2026-11-14T10:00Z"}])
    assert (a.status, a.level, a.trigger, a.rule_id) == ("act", 2, "sep", "radiation_spe")
    assert a.event_id == "2026-11-14T10:00:00-SEP-001"
    assert a.event_time == datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def test_sep_older_than_24h_is_ok():
    a = ev(sep=[{"sepID": "x", "eventTime": "2026-11-13T11:59Z"}])
    assert (a.status, a.level) == ("ok", 0)


def test_x_flare_is_watch():
    a = ev(flr=[{"flrID": "f", "classType": "X1.2", "peakTime": "2026-11-14T08:00Z"}])
    assert (a.status, a.level, a.trigger, a.rule_id) == ("watch", 1, "flare_x", "radiation_spe")


def test_m_flare_is_ok():
    a = ev(flr=[{"flrID": "f", "classType": "M9.9", "peakTime": "2026-11-14T08:00Z"}])
    assert a.status == "ok"


def test_kp7_is_watch():
    g = [{"gstID": "g", "allKpIndex": [{"kpIndex": 7, "observedTime": "2026-11-14T03:00Z"}]}]
    a = ev(gst=g)
    assert (a.status, a.level, a.trigger) == ("watch", 1, "gst_kp7")


def test_kp_6_67_is_ok():
    g = [{"gstID": "g", "allKpIndex": [{"kpIndex": 6.67, "observedTime": "2026-11-14T03:00Z"}]}]
    assert ev(gst=g).status == "ok"


def test_act_wins_over_watch():
    a = ev(
        sep=[{"sepID": "s", "eventTime": "2026-11-14T09:00Z"}],
        flr=[{"flrID": "f", "classType": "X2.0", "peakTime": "2026-11-14T08:00Z"}],
    )
    assert (a.status, a.trigger) == ("act", "sep")


def test_all_empty_is_ok():
    a = ev()
    assert (a.status, a.level, a.trigger, a.rule_id) == ("ok", 0, None, "radiation_spe")


def test_missing_kind_is_unknown():
    a = evaluate_space_weather({"FLR": [], "SEP": None, "GST": []}, NOW)
    assert (a.status, a.level) == ("unknown", None)


def test_future_event_is_ignored():
    assert ev(sep=[{"sepID": "s", "eventTime": "2026-11-14T13:00Z"}]).status == "ok"


def test_link_passthrough():
    a = ev(sep=[{"sepID": "s", "eventTime": "2026-11-14T10:00Z", "link": "https://x/y"}])
    assert a.link == "https://x/y"


def test_committed_replay_triggers_act():
    rp = load_replay(REPLAY)
    a = evaluate_space_weather(rp.events, rp.replay_now)
    assert a.status == "act"
    assert a.event_time.date().isoformat() == "2025-11-10"
