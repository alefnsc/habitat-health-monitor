"""Hosting entry point for the public ground segment (D38)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ground"))

from receiver.cloud import create_cloud_app
from receiver.redis_store import RedisStore
from receiver.upstash_kv import UpstashKV

app = create_cloud_app(RedisStore(UpstashKV.from_env()), os.environ.get("GROUND_INGEST_SECRET", ""))
