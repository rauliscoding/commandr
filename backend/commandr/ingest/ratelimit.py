"""Fixed-window rate limits in the shared cache (Redis in production).

Always keyed by a tenant identity — an ingest key or a heartbeat — never a
global bucket and never the client IP behind the proxy (CLAUDE.md invariant 4).
"""

from __future__ import annotations

import time

from django.core.cache import cache

WINDOW = 60


def hit(identity: str, limit: int) -> int | None:
    """Count one request. Return seconds to wait if over `limit`, else None."""
    now = int(time.time())
    window = now - now % WINDOW
    key = f"ingest:rl:{identity}:{window}"
    if cache.add(key, 1, WINDOW + 5):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.add(key, 1, WINDOW + 5)
            count = 1
    if count > limit:
        return max(1, window + WINDOW - now)
    return None
