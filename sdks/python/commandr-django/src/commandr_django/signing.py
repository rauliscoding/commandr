# SPDX-License-Identifier: AGPL-3.0-only
"""Verifying Commandr's poll signature (ingestion contract § 1).

    X-Commandr-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<METHOD>.<path>")>

Must stay byte-for-byte compatible with the server's
`backend/commandr/monitoring/signing.py`; the SDK's tests sign with that file.
"""

from __future__ import annotations

import hashlib
import hmac

TOLERANCE_SECONDS = 300


def _mac(secret: str, timestamp: int, method: str, path: str) -> str:
    message = f"{timestamp}.{method.upper()}.{path}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(secret: str, header: str, method: str, path: str, now: int) -> bool:
    """True if `header` signs this method and path with `secret`, within 300 s of `now`."""
    if not secret or not header:
        return False
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(now - timestamp) > TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(given.encode(), _mac(secret, timestamp, method, path).encode())
