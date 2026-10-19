"""Heartbeat state: what a ping means, and when silence becomes a failure."""

from __future__ import annotations

from datetime import datetime, timedelta

from commandr.core.logging import redact
from commandr.integrations.services import mark_data_received
from commandr.monitoring import checks
from commandr.monitoring.models import CheckSource, CheckStatus

from .models import Heartbeat, HeartbeatPing, PingKind

MAX_MESSAGE = 1000


def _ago(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return f"{seconds} s ago"
    if seconds < 90 * 60:
        return f"{seconds // 60} min ago"
    if seconds < 36 * 3600:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


def every(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} day{'s' if seconds != 86400 else ''}"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    return f"{seconds // 60} min"


def status(hb: Heartbeat, now: datetime) -> checks.Result:
    """ok / fail / unknown for one heartbeat, and why, in words."""
    if hb.last_fail_at and (hb.last_ping_at is None or hb.last_fail_at >= hb.last_ping_at):
        detail = f": {hb.last_message}" if hb.last_message else ""
        return checks.Result(
            "heartbeat", hb.name, CheckStatus.FAIL, f"Last run reported a failure{detail}"
        )
    if hb.last_ping_at is None:
        return checks.Result(
            "heartbeat", hb.name, CheckStatus.UNKNOWN, "Waiting for the first ping."
        )
    deadline = hb.last_ping_at + timedelta(seconds=hb.period_seconds + hb.grace_seconds)
    if now > deadline:
        return checks.Result(
            "heartbeat",
            hb.name,
            CheckStatus.FAIL,
            f"Last ping {_ago(now - hb.last_ping_at)}; expected every {every(hb.period_seconds)}.",
        )
    return checks.Result(
        "heartbeat", hb.name, CheckStatus.OK, f"Last ping {_ago(now - hb.last_ping_at)}."
    )


def refresh_check(hb: Heartbeat, now: datetime) -> None:
    checks.record(
        project=hb.project,
        source=CheckSource.HEARTBEAT,
        source_id=hb.id,
        result=status(hb, now),
        now=now,
    )


def record_ping(hb: Heartbeat, kind: str, now: datetime, message: str = "") -> None:
    """Store a ping, update the heartbeat, its check and its connection."""
    message = redact(message)[:MAX_MESSAGE]
    duration_ms: int | None = None
    if kind == PingKind.START:
        hb.last_start_at = now
    else:
        # A run's duration is measured from a start that no success or failure
        # has closed yet.
        start = hb.last_start_at
        if start and all(t is None or start > t for t in (hb.last_ping_at, hb.last_fail_at)):
            duration_ms = int((now - start).total_seconds() * 1000)
            hb.last_duration_ms = duration_ms
        if kind == PingKind.SUCCESS:
            hb.last_ping_at = now
            hb.last_message = ""
        else:
            hb.last_fail_at = now
            hb.last_message = message
    hb.save()
    HeartbeatPing.objects.create(
        heartbeat=hb, kind=kind, ts=now, duration_ms=duration_ms, message=message
    )
    if kind != PingKind.START:
        refresh_check(hb, now)
    mark_data_received(hb.connection, at=now)
