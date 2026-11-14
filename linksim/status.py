"""Link state endpoint: GET /link/state (D16), served on a daemon thread."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .engine import LinkEngine


def serve_status(
    engine: LinkEngine, host: str, port: int, clock: Callable[[], float]
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?")[0] != "/link/state":
                self.send_error(404)
                return
            body = json.dumps(engine.snapshot(clock()).to_dict()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # silence per-request logging
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
