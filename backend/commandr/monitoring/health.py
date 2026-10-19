"""One project's health right now: what the Health page and the digest show."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from commandr.ingest import heartbeats as hb_state
from commandr.ingest.models import Heartbeat
from commandr.tenancy.models import Project

from .models import Check, CheckStatus, MetricKind, MetricSeries, UptimeMonitor

RECENT = timedelta(hours=24)
_ORDER = {CheckStatus.FAIL: 0, CheckStatus.WARN: 1, CheckStatus.UNKNOWN: 2, CheckStatus.OK: 3}


class Verdict:
    HEALTHY = "healthy"
    ATTENTION = "attention"
    NOTHING_CHECKED = "nothing_checked"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def verdict(checks: list[Check], now: datetime, *, alerts_recently: int = 0) -> dict[str, Any]:
    """Three verdicts, never two: "nothing was checked" is not "healthy"."""
    ran = [c.last_run_at for c in checks if c.last_run_at and now - c.last_run_at <= RECENT]
    counts = {s: sum(1 for c in checks if c.status == s) for s in CheckStatus.values}
    if not ran:
        state = Verdict.NOTHING_CHECKED
    elif counts["fail"] or counts["warn"] or counts["unknown"] or alerts_recently:
        state = Verdict.ATTENTION
    else:
        state = Verdict.HEALTHY
    return {
        "state": state,
        "failing": counts["fail"],
        "warning": counts["warn"],
        "unknown": counts["unknown"],
        "ok": counts["ok"],
        "last_checked_at": _iso(max(ran) if ran else None),
    }


def snapshot(project: Project, now: datetime) -> dict[str, Any]:
    checks = sorted(
        Check.objects.filter(project=project), key=lambda c: (_ORDER[CheckStatus(c.status)], c.name)
    )
    heartbeats = []
    for hb in Heartbeat.objects.filter(project=project).order_by("name"):
        result = hb_state.status(hb, now)
        heartbeats.append(
            {
                "id": str(hb.id),
                "name": hb.name,
                "period_seconds": hb.period_seconds,
                "grace_seconds": hb.grace_seconds,
                "status": result.status,
                "summary": result.summary,
                "last_ping_at": _iso(hb.last_ping_at),
                "last_fail_at": _iso(hb.last_fail_at),
                "last_duration_ms": hb.last_duration_ms,
                "next_due_at": _iso(
                    hb.last_ping_at + timedelta(seconds=hb.period_seconds)
                    if hb.last_ping_at
                    else None
                ),
            }
        )
    kpis = [
        {
            "name": s.name,
            "label": s.label or s.name,
            "unit": s.unit,
            # NULL stays null all the way to the screen, which renders "—".
            "value": s.last_value,
            "as_of": _iso(s.last_at),
        }
        for s in MetricSeries.objects.filter(project=project, kind=MetricKind.KPI).order_by(
            "label", "name"
        )
    ]
    uptime = [
        {
            "id": str(m.id),
            "url": m.url,
            "interval_seconds": m.interval_seconds,
            "last_run_at": _iso(m.last_run_at),
            "last_status_code": m.last_status_code,
            "last_response_ms": m.last_response_ms,
            "tls_expires_at": _iso(m.tls_expires_at),
            "last_error": m.last_error,
        }
        for m in UptimeMonitor.objects.filter(project=project).order_by("url")
    ]
    return {
        "generated_at": now.isoformat(),
        "verdict": verdict(checks, now),
        "checks": [
            {
                "id": str(c.id),
                "name": c.name,
                "key": c.key,
                "source": c.source,
                "status": c.status,
                "summary": c.summary,
                "value": c.value,
                "unit": c.unit,
                "last_run_at": _iso(c.last_run_at),
                "changed_at": _iso(c.changed_at),
            }
            for c in checks
        ],
        "heartbeats": heartbeats,
        "kpis": kpis,
        "uptime": uptime,
    }
