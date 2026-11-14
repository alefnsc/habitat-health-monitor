import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from hub.nasa.config import NasaSettings
from hub.nasa.donki import (
    POLL_INTERVAL_S,
    DonkiResult,
    DonkiUnavailable,
    poll_once,
    run_poller,
)
from hub.nasa.donki_cache import DonkiCache, is_stale

BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _res(kind="SEP", at=T, events=None):
    return DonkiResult(kind, events if events is not None else [{"a": 1}, {"a": 2}], "direct", at)


def test_write_then_read_roundtrip(tmp_path):
    c = DonkiCache(tmp_path)
    c.write(_res())
    got = c.read("SEP")
    assert got.events == [{"a": 1}, {"a": 2}]
    assert got.cached_at == T and got.route == "direct"


def test_read_missing_returns_none(tmp_path):
    assert DonkiCache(tmp_path).read("FLR") is None


def test_read_corrupt_returns_none(tmp_path, caplog):
    (tmp_path / "donki_FLR.json").write_text("not json")
    with caplog.at_level(logging.WARNING):
        assert DonkiCache(tmp_path).read("FLR") is None
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_write_is_atomic(tmp_path):
    c = DonkiCache(tmp_path)
    old = T - timedelta(hours=2)
    c.write(_res(at=old))
    with pytest.raises(TypeError):
        c.write(_res(events=[{"when": datetime.now(UTC)}]))
    assert c.read("SEP").cached_at == old
    assert [p.name for p in tmp_path.iterdir()] == ["donki_SEP.json"]


def test_stale_boundary():
    assert not is_stale(T, T + timedelta(minutes=30))
    assert is_stale(T, T + timedelta(minutes=30, seconds=1))


def test_notifications_message_body_stripped(tmp_path):
    c = DonkiCache(tmp_path)
    c.write(_res("notifications", events=[{"messageID": "x", "messageBody": "long" * 100}]))
    assert "messageBody" not in c.read("notifications").events[0]


def _settings(tmp_path, mode="live"):
    return NasaSettings(var_dir=tmp_path, donki_mode=mode)


@pytest.mark.asyncio
async def test_poll_uses_7_day_window(tmp_path):
    with respx.mock() as r:
        for k in ("FLR", "SEP", "GST", "notifications"):
            r.get(f"{BASE}/{k}").respond(json=[])
        async with httpx.AsyncClient() as client:
            out = await poll_once(
                T, cache=DonkiCache(tmp_path), client=client, settings=_settings(tmp_path)
            )
        assert r.calls.call_count == 4
        for call in r.calls:
            q = call.request.url.params
            assert q["startDate"] == "2026-11-07" and q["endDate"] == "2026-11-14"
    assert set(out) == {"FLR", "SEP", "GST", "notifications"}


@pytest.mark.asyncio
async def test_poll_failure_keeps_previous_cache(tmp_path):
    cache = DonkiCache(tmp_path)
    cache.write(_res("SEP", at=T - timedelta(hours=2)))
    later = T - timedelta(hours=1, minutes=50)
    with respx.mock() as r:
        r.get(f"{BASE}/SEP").respond(503)
        for k in ("FLR", "GST", "notifications"):
            r.get(f"{BASE}/{k}").respond(json=[])
        async with httpx.AsyncClient() as client:
            await poll_once(later, cache=cache, client=client, settings=_settings(tmp_path))
    assert cache.read("SEP").cached_at == T - timedelta(hours=2)
    assert cache.read("FLR").cached_at == later


async def _one_cycle(tmp_path, *, settings, after_poll):
    stop = asyncio.Event()
    calls = []

    async def cb(now):
        calls.append(now)
        stop.set()

    cbs = [cb] if after_poll is None else [after_poll, cb]
    async with httpx.AsyncClient() as client:
        await asyncio.wait_for(
            run_poller(
                stop,
                settings=settings,
                cache=DonkiCache(tmp_path),
                client=client,
                clock=lambda: T,
                after_poll=cbs,
                interval_s=POLL_INTERVAL_S,
            ),
            5,
        )
    return calls


@pytest.mark.asyncio
async def test_poller_runs_after_poll_even_on_failure(tmp_path):
    with respx.mock() as r:
        r.get(url__startswith=BASE).respond(503)
        calls = await _one_cycle(tmp_path, settings=_settings(tmp_path), after_poll=None)
    assert calls == [T]


@pytest.mark.asyncio
async def test_after_poll_exception_is_logged(tmp_path, caplog):
    async def bad(now):
        raise RuntimeError("boom")

    with respx.mock() as r, caplog.at_level(logging.ERROR):
        r.get(url__startswith=BASE).respond(json=[])
        calls = await _one_cycle(tmp_path, settings=_settings(tmp_path), after_poll=bad)
    assert calls == [T]
    assert len([x for x in caplog.records if x.levelno == logging.ERROR]) == 1


@pytest.mark.asyncio
async def test_replay_mode_skips_network(tmp_path):
    with respx.mock(assert_all_called=False) as r:
        calls = await _one_cycle(tmp_path, settings=_settings(tmp_path, "replay"), after_poll=None)
        assert r.calls.call_count == 0
    assert calls == [T]


def test_donki_unavailable_is_importable():
    assert issubclass(DonkiUnavailable, Exception)
