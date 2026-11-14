from receiver.upstash_kv import UpstashKV


class FakeClient:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **kw):
            self.calls.append((name, a, kw))
            return [] if name == "zrange" else None
        return call


def test_adapter_maps_calls():
    c = FakeClient()
    kv = UpstashKV(c)
    kv.set("k", "v", ex=10)
    kv.zadd("z", {"m": 1.0})
    kv.zrangebyscore("z", 2, "+inf", offset=0, count=5)
    kv.zremrangebyscore("z", 1, 1)
    kv.expire("z", 10)
    names = [n for n, _, _ in c.calls]
    assert names == ["set", "zadd", "zrange", "zremrangebyscore", "expire"]
    assert c.calls[0][2].get("ex") == 10


def test_from_env_prefers_upstash_then_kv(monkeypatch):
    seen = {}

    class R:
        def __init__(self, url, token):
            seen["url"], seen["token"] = url, token

    monkeypatch.setattr("receiver.upstash_kv._redis_class", lambda: R)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.setenv("KV_REST_API_URL", "https://a")
    monkeypatch.setenv("KV_REST_API_TOKEN", "t")
    UpstashKV.from_env()
    assert seen == {"url": "https://a", "token": "t"}
