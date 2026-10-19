# SPDX-License-Identifier: AGPL-3.0-only
"""Commandr for Django: a signed status endpoint, traffic, errors, KPIs and heartbeats.

    import commandr_django as commandr

    @commandr.check("disk:External", name="External volume")
    def external_volume(): ...

    @commandr.kpi("user.total", label="Users", unit="count")
    def users_total(): ...

The SDK never blocks or raises into the host app.
"""

from .events import event
from .handler import CommandrHandler
from .heartbeat import heartbeat, ping
from .registry import Check, check, gauge, kpi


def flush(timeout: float | None = None) -> None:
    """Send what is buffered now (for short-lived scripts; the SDK flushes at exit too)."""
    from .transport import transport

    transport.flush(timeout)


__version__ = "0.1.0"
__all__ = [
    "Check",
    "CommandrHandler",
    "check",
    "event",
    "flush",
    "gauge",
    "heartbeat",
    "kpi",
    "ping",
]
