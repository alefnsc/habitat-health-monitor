"""N1 DONKI client tests.

Probes run 2026-11-14 against the keyless CCMC host:
- GET https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP?startDate=2025-11-01&endDate=2025-11-30 -> 200
- GET https://ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP?startDate=2025-11-01&endDate=2025-11-30 -> 200
  (both work; the plan's verified path /DONKI-API/get is the default)
- FLR with startDate=2026-09-02 endDate=2026-11-01 (60 days) -> 200
- FLR with startDate=2026-09-01 endDate=2026-11-01 (61 days) -> 400
  "API Error: Date range cannot exceed 60 days. You requested 61 days."
"""

from datetime import date

import httpx
import pytest
import respx

from hub.nasa.donki import DonkiUnavailable, donki_fetch, donki_url, main

BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
API = "https://api.nasa.gov/DONKI/SEP"
START, END = date(2026, 9, 2), date(2026, 11, 1)


def test_url_has_no_trailing_slash():
    assert donki_url(BASE, "SEP", date(2025, 11, 1), date(2025, 11, 30)) == (
        "https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP?startDate=2025-11-01&endDate=2025-11-30"
    )


async def _fetch(kind="SEP", key=None, start=START, end=END):
    async with httpx.AsyncClient(timeout=10) as c:
        return await donki_fetch(kind, start, end, client=c, base=BASE, api_key=key)


@pytest.mark.asyncio
async def test_rejects_61_day_window():
    with respx.mock(assert_all_called=False) as r:
        with pytest.raises(ValueError):
            await _fetch("FLR", start=date(2026, 9, 1))
        assert r.calls.call_count == 0


@pytest.mark.asyncio
async def test_accepts_60_day_window():
    with respx.mock() as r:
        r.get(f"{BASE}/FLR").respond(json=[])
        await _fetch("FLR")
        assert r.calls.call_count == 1


@pytest.mark.asyncio
async def test_rejects_unknown_kind():
    with respx.mock(assert_all_called=False) as r:
        with pytest.raises(ValueError):
            await _fetch("CME")
        assert r.calls.call_count == 0


@pytest.mark.asyncio
async def test_empty_array_is_quiet_not_error():
    with respx.mock(assert_all_called=False) as r:
        r.get(f"{BASE}/SEP").respond(json=[])
        api = r.get(API).respond(json=[{"x": 1}])
        res = await _fetch(key="abc123")
        assert res.events == [] and res.route == "direct"
        assert not api.called


@pytest.mark.asyncio
async def test_falls_back_to_key_route_on_5xx():
    with respx.mock() as r:
        r.get(f"{BASE}/SEP").respond(503)
        api = r.get(API).respond(json=[{"sepID": "a"}])
        res = await _fetch(key="abc123")
        assert res.route == "api_key" and res.events == [{"sepID": "a"}]
        q = api.calls[0].request.url.params
        assert q["startDate"] == "2026-09-02" and q["endDate"] == "2026-11-01"
        assert q["api_key"] == "abc123"


@pytest.mark.asyncio
async def test_falls_back_on_timeout():
    with respx.mock() as r:
        r.get(f"{BASE}/SEP").mock(side_effect=httpx.ReadTimeout("t"))
        r.get(API).respond(json=[])
        assert (await _fetch(key="abc123")).route == "api_key"


@pytest.mark.asyncio
async def test_never_uses_demo_key():
    with respx.mock(assert_all_called=False) as r:
        r.get(f"{BASE}/SEP").respond(503)
        api = r.get(API).respond(json=[])
        with pytest.raises(DonkiUnavailable):
            await _fetch(key="DEMO_KEY")
        assert not api.called


@pytest.mark.asyncio
async def test_no_key_no_second_route():
    with respx.mock() as r:
        r.get(f"{BASE}/SEP").respond(503)
        with pytest.raises(DonkiUnavailable):
            await _fetch(key=None)


@pytest.mark.asyncio
async def test_gateway_flr_404_is_unavailable():
    with respx.mock() as r:
        r.get(f"{BASE}/FLR").respond(503)
        r.get("https://api.nasa.gov/DONKI/FLR").respond(404)
        with pytest.raises(DonkiUnavailable):
            await _fetch("FLR", key="abc123")


@pytest.mark.asyncio
async def test_key_never_in_exception_text():
    with respx.mock() as r:
        r.get(f"{BASE}/SEP").respond(503)
        r.get(API).respond(500)
        with pytest.raises(DonkiUnavailable) as e:
            await _fetch(key="secretkey99")
        assert "secretkey99" not in str(e.value)


def test_cli_rejects_long_window_without_network(capsys):
    with respx.mock(assert_all_called=False) as r:
        code = main(["SEP", "2025-09-01", "2025-11-30"])
        assert r.calls.call_count == 0
    assert code != 0
    assert "window exceeds 60 days" in capsys.readouterr().err
