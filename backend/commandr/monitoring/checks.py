"""Recording check results and driving the alert state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings

from commandr.tenancy.models import Project

from . import notify
from .alerts import Action, on_disappear, transition
from .models import Check, CheckStatus

STALE_AFTER_INTERVALS = 3


@dataclass(frozen=True)
class Result:
    key: str
    name: str
    status: str
    summary: str = ""
    value: float | None = None
    unit: str = ""


def cooldown() -> timedelta:
    return timedelta(minutes=settings.MONITORING_ALERT_COOLDOWN_MINUTES)


def _apply_alerting(check: Check, now: datetime) -> None:
    state, action = transition(
        alert_state=check.alert_state,
        last_notified_at=check.last_notified_at,
        status=check.status,
        now=now,
        cooldown=cooldown(),
    )
    if action is not None:
        notify.notify_check(check, action, now)
        check.last_notified_at = now
        if action is Action.ALERT:
            check.alerted_at = now
    check.alert_state = state


def record(
    *,
    project: Project,
    source: str,
    source_id: UUID,
    result: Result,
    now: datetime,
    expected_every_seconds: int | None = None,
) -> Check:
    """Upsert a check's latest result and send whatever the transition calls for."""
    check, _ = Check.objects.select_for_update().get_or_create(
        project=project,
        source=source,
        source_id=source_id,
        key=result.key,
        defaults={"name": result.name},
    )
    check.project = project  # already loaded: avoids a query when notifying
    if check.status != result.status or check.changed_at is None:
        check.changed_at = now
    check.name = result.name[:200]
    check.status = result.status
    check.summary = result.summary[:500]
    check.value = result.value
    check.unit = result.unit[:32]
    check.last_run_at = now
    check.expected_every_seconds = expected_every_seconds
    _apply_alerting(check, now)
    check.save()
    return check


def retire(check: Check, now: datetime) -> None:
    """The source stopped reporting this check: recovered, then forgotten."""
    action = on_disappear(check.alert_state)
    if action is not None:
        check.status = CheckStatus.OK
        notify.notify_check(check, action, now)
    check.delete()


def mark_stale(project_id: UUID, now: datetime) -> int:
    """Checks whose source went quiet turn unknown — never stay "ok" by default."""
    count = 0
    candidates = Check.objects.filter(
        project_id=project_id, expected_every_seconds__isnull=False
    ).exclude(status=CheckStatus.UNKNOWN)
    for check in candidates.select_for_update(of=("self",)).select_related("project"):
        if check.expected_every_seconds is None:  # filtered above; for the type checker
            continue
        limit = timedelta(seconds=check.expected_every_seconds * STALE_AFTER_INTERVALS)
        if check.last_run_at is None or now - check.last_run_at > limit:
            check.status = CheckStatus.UNKNOWN
            check.summary = "No result recently: the source has not reported."
            check.changed_at = now
            _apply_alerting(check, now)
            check.save(
                update_fields=[
                    "status",
                    "summary",
                    "changed_at",
                    "alert_state",
                    "alerted_at",
                    "last_notified_at",
                ]
            )
            count += 1
    return count
