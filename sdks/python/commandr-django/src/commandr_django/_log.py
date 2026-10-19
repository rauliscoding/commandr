# SPDX-License-Identifier: AGPL-3.0-only
"""The SDK's own logging: WARNING at most, and at most once a minute per topic.

A monitoring library that floods the host's logs when Commandr is unreachable
would be its own incident.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("commandr_django")

INTERVAL_SECONDS = 60.0
_last: dict[str, float] = {}
_lock = threading.Lock()


def warn(topic: str, message: str, *args: object) -> None:
    """Log at WARNING unless `topic` was logged in the last minute."""
    now = time.monotonic()
    with _lock:
        previous = _last.get(topic)
        if previous is not None and now - previous < INTERVAL_SECONDS:
            return
        _last[topic] = now
    logger.warning(message, *args)


def reset() -> None:
    """For tests."""
    with _lock:
        _last.clear()
