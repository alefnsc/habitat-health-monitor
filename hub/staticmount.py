"""Static build mounts that answer 503 until the build exists (D14)."""

from __future__ import annotations

from pathlib import Path

from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send


class BuildMount:
    def __init__(self, directory: Path, build_hint: str) -> None:
        self.directory = Path(directory)
        self.build_hint = build_hint
        self._files: StaticFiles | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (self.directory / "index.html").is_file():
            resp = PlainTextResponse(f"Not built yet. Run: {self.build_hint}", status_code=503)
            await resp(scope, receive, send)
            return
        if self._files is None:
            self._files = StaticFiles(directory=self.directory, html=True)
        await self._files(scope, receive, send)
