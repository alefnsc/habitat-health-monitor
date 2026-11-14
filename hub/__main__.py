"""python -m hub: run the hub with uvicorn."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from hub.config import load_settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hub", description="Habitat hub")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings(os.environ)
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path("var").mkdir(exist_ok=True)
    host = args.host or settings.http_host
    port = args.port or settings.http_port
    log = logging.getLogger("hub")
    log.info(
        "starting hub on %s:%s db=%s mqtt=%s:%s features=%s crews=%s",
        host, port, settings.db_path, settings.mqtt_host, settings.mqtt_port,
        ",".join(sorted(settings.features)), ",".join(settings.crews),
    )  # fmt: skip

    import uvicorn

    uvicorn.run("hub.api:app_factory", factory=True, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
