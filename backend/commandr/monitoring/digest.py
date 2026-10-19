"""The daily digest: sent whether or not anything is wrong (silence is a signal).

Three verdicts, so a project where nothing ran never reads as healthy:
healthy · needs attention · nothing was checked.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.template.loader import render_to_string

from commandr.tenancy.models import Project

from . import notify
from .health import RECENT, Verdict, snapshot, verdict
from .models import Check, Notification, NotificationKind

_HEADLINE = {
    Verdict.HEALTHY: "Healthy",
    Verdict.ATTENTION: "Needs attention",
    Verdict.NOTHING_CHECKED: "Nothing was checked",
}


def build(project: Project, now: datetime) -> dict[str, Any]:
    data = snapshot(project, now)
    alerts = Notification.objects.filter(
        project=project, kind=NotificationKind.ALERT, created_at__gte=now - RECENT
    ).count()
    data["verdict"] = verdict(
        list(Check.objects.filter(project=project)), now, alerts_recently=alerts
    )
    data["alerts_24h"] = alerts
    data["headline"] = _HEADLINE[data["verdict"]["state"]]
    data["attention"] = [c for c in data["checks"] if c["status"] != "ok"]
    data["project"] = project
    data["health_url"] = notify.health_url(project)
    return data


def send(project: Project, now: datetime, local_day: date) -> Notification | None:
    """Queue today's digest for `project`; None if it was already queued."""
    context = build(project, now)
    context["local_day"] = local_day
    return notify.create(
        project=project,
        kind=NotificationKind.DIGEST,
        dedupe_key=f"digest:{project.id}:{local_day.isoformat()}",
        subject=f"{project.name} daily digest: {context['headline']}",
        text=render_to_string("monitoring/email/digest.txt", context),
        html=render_to_string("monitoring/email/digest.html", context),
    )
