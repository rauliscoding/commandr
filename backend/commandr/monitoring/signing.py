"""Signing status-endpoint polls (ingestion contract § Status endpoint).

    X-Commandr-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<METHOD>.<path>")>

`path` is the URL path exactly as requested, without the query string. The
customer's app verifies in constant time and rejects |now - t| > 300 s.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlsplit

TOLERANCE_SECONDS = 300


def signed_path(url: str) -> str:
    return urlsplit(url).path or "/"


def _mac(secret: str, timestamp: int, method: str, path: str) -> str:
    message = f"{timestamp}.{method.upper()}.{path}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def sign(secret: str, method: str, path: str, timestamp: int) -> str:
    return f"t={timestamp},v1={_mac(secret, timestamp, method, path)}"


def verify(secret: str, header: str, method: str, path: str, now: int) -> bool:
    """What the customer side does (and the SDK will do). Used by our tests."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(now - timestamp) > TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(given, _mac(secret, timestamp, method, path))
