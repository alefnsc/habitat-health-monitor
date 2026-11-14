from datetime import UTC, datetime, timedelta

import pytest

from hub.nasa.isslive import ISS_ITEMS, IssLiveState, iss_timestamp_to_utc, parse_value


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_items():
    assert ISS_ITEMS == {
        "USLAB000058": "cabin_pressure",
        "USLAB000059": "cabin_temperature",
        "USLAB000055": "lab_ppco2",
        "NODE3000003": "node3_ppco2",
    }
    assert "TIME_000001" not in ISS_ITEMS


def test_timestamp_day317():
    assert iss_timestamp_to_utc(7630.65, utc(2026, 11, 13, 23)) == utc(2026, 11, 13, 22, 39)


def test_timestamp_seconds():
    got = iss_timestamp_to_utc(7631.1147, utc(2026, 11, 13, 23, 10))
    assert abs(got - utc(2026, 11, 13, 23, 6, 52, 900000)) < timedelta(seconds=0.1)


def test_timestamp_nov2():
    got = iss_timestamp_to_utc(7359.02, utc(2026, 11, 13, 23))
    assert abs(got - utc(2026, 11, 2, 15, 1, 12)) < timedelta(seconds=1)


def test_timestamp_year_boundary():
    assert iss_timestamp_to_utc(8783.0, utc(2027, 1, 1, 0, 30)) == utc(2026, 12, 31, 23)


@pytest.mark.parametrize("raw", ["", None, "n/a"])
def test_parse_value_bad(raw):
    assert parse_value(raw) is None


def test_parse_value():
    assert parse_value("759.26") == 759.26


def test_state_keeps_latest_per_item():
    s = IssLiveState()
    now = utc(2026, 11, 13, 23)
    s.update("USLAB000058", "7630.65", "759.10", "Normal", now)
    s.update("USLAB000058", "7630.70", "759.26", "Normal", now)
    assert s.latest()["USLAB000058"].val == 759.26


def test_unparseable_update_ignored():
    s = IssLiveState()
    now = utc(2026, 11, 13, 23)
    s.update("USLAB000058", "7630.65", "759.10", "Normal", now)
    assert s.update("USLAB000058", "7630.70", "", "Normal", now) is False
    assert s.latest()["USLAB000058"].val == 759.10


def test_update_sets_last_message_at():
    s = IssLiveState()
    t = utc(2026, 11, 13, 12)
    s.update("USLAB000059", "7620.5", "23.26", None, t)
    assert s.last_message_at == t
    assert s.latest()["USLAB000059"].measured_at == utc(2026, 11, 13, 12, 30)
