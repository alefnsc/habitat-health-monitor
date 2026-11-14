"""HMAC-SHA256 body signatures for the public ingest (D38)."""

from __future__ import annotations

import hashlib
import hmac

HEADER = "X-Habitat-Signature"


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header:
        return False
    return hmac.compare_digest(sign(body, secret), header)
