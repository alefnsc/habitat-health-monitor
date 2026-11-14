"""The ring's cloud API: three /v2/usercollection/ endpoints, paged with next_token (D41 §2, §3).

Refresh tokens are single-use, so a refreshed token is saved before the request is retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from nodes.ring.auth import (
    USER_AGENT,
    AuthError,
    OAuthConfig,
    load_token,
    refresh_token,
    save_token,
)

HEARTRATE = "/v2/usercollection/heartrate"
SLEEP = "/v2/usercollection/sleep"
DAILY_SPO2 = "/v2/usercollection/daily_spo2"
REFRESH_MARGIN_S = 60


class RingApiError(RuntimeError):
    pass


class RingClient:
    def __init__(
        self,
        cfg: OAuthConfig,
        base: str,
        token_path: Path,
        http: httpx.Client,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg, self.base, self.token_path, self.http, self.clock = (
            cfg, base.rstrip("/"), Path(token_path), http, clock
        )  # fmt: skip
        self._tok: dict | None = None

    def _token(self) -> dict:
        if self._tok is None:
            self._tok = load_token(self.token_path)
            if self._tok["expires_at"] <= self.clock() + REFRESH_MARGIN_S:
                self._refresh()
        assert self._tok is not None
        return self._tok

    def _refresh(self) -> None:
        assert self._tok is not None
        self._tok = refresh_token(self.cfg, self._tok["refresh_token"], self.http, now=self.clock())
        save_token(self.token_path, self._tok)

    def _get(self, path: str, params: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()['access_token']}", "User-Agent": USER_AGENT}
        return self.http.get(self.base + path, params=params, headers=headers, timeout=30)

    def get_all(self, path: str, params: dict) -> list[dict]:
        data: list[dict] = []
        page: dict = dict(params)
        refreshed = False
        while True:
            res = self._get(path, page)
            if res.status_code == 401 and not refreshed:
                refreshed = True
                self._refresh()
                continue
            if res.status_code == 401:
                raise AuthError("401 after a refresh: run `python -m nodes.ring auth` again")
            if res.status_code != 200:
                tier = res.headers.get("X-RateLimit-Tier", "")
                raise RingApiError(f"{path} answered {res.status_code} {tier}: {res.text[:200]}".strip())
            body = res.json()
            data.extend(body.get("data") or [])
            token = body.get("next_token")
            if not token:
                return data
            page = {**params, "next_token": token}

    def fetch_window(self, start: datetime, end: datetime) -> dict[str, list[dict]]:
        """Raw documents for [start, end]; the day-based endpoints get end_date + 1 day."""
        days = {"start_date": start.date().isoformat(),
                "end_date": (end.date() + timedelta(days=1)).isoformat()}  # fmt: skip
        return {
            "heartrate": self.get_all(
                HEARTRATE, {"start_datetime": start.isoformat(), "end_datetime": end.isoformat()}
            ),
            "sleep": self.get_all(SLEEP, days),
            "daily_spo2": self.get_all(DAILY_SPO2, days),
        }
