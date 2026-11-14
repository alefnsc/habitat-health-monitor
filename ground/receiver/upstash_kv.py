"""KV adapter over the Upstash REST client (MIT). Only the public deployment uses it."""

from __future__ import annotations

import os


def _redis_class():
    from upstash_redis import Redis

    return Redis


class UpstashKV:
    def __init__(self, client) -> None:
        self.r = client

    @classmethod
    def from_env(cls) -> UpstashKV:
        url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL", "")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN", "")
        return cls(_redis_class()(url=url, token=token))

    def get(self, key):
        return self.r.get(key)

    def set(self, key, value, ex):
        self.r.set(key, value, ex=ex)

    def expire(self, key, seconds):
        self.r.expire(key, seconds)

    def delete(self, key):
        self.r.delete(key)

    def zadd(self, key, members):
        self.r.zadd(key, members)

    def zrangebyscore(self, key, lo, hi, offset=0, count=None):
        kw = {"sortby": "BYSCORE"}
        if count is not None:
            kw.update(offset=offset, count=count)
        return list(self.r.zrange(key, lo, hi, **kw))

    def zremrangebyscore(self, key, lo, hi):
        self.r.zremrangebyscore(key, lo, hi)
