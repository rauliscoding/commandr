"""Building and sending notification emails (Django SMTP → Resend).

Notifications are written to an outbox row in the same transaction as the
change that caused them, and a task sends them after commit. Re-running the
task never sends twice (`sent_at`); creating the same notification twice is a
no-op (`dedupe_key`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from commandr.tenancy.models import Membership, Project, Role

from .alerts import Action
from .models import Check, Notification, NotificationKind

_SUBJECT = {
    Action.ALERT: "{project}: {check} is failing",
    Action.REMINDER: "{project}: {check} is still failing",
    Action.RECOVERY: "{project}: {check} is passing again",
}


def health_url(project: Project) -> str:
    return f"{settings.APP_ORIGIN}/o/{project.organization_id}/p/{project.id}/health"


def recipients(organization_id: UUID) -> list[str]:
    """Owners and admins. Memberships are not under RLS; always filtered by org."""
    return list(
        Membership.objects.filter(
            organization_id=organization_id,
            role__in=[Role.OWNER, Role.ADMIN],
            user__is_active=True,
        )
        .order_by("created_at")
        .values_list("user__email", flat=True)
    )


def queue(notification: Notification) -> None:
    """Send after the surrounding transaction commits (the row must be visible)."""
    from .tasks import send_notification

    org_id = str(notification.organization_id)
    nid = str(notification.id)
    transaction.on_commit(lambda: send_notification.delay(nid, org_id))


def create(
    *, project: Project, kind: str, dedupe_key: str, subject: str, text: str, html: str = ""
) -> Notification | None:
    """Create and queue a notification once per `dedupe_key`; None if it existed."""
    notification, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "project": project,
            "kind": kind,
            "subject": subject[:200],
            "body_text": text,
            "body_html": html,
        },
    )
    if not created:
        return None
    queue(notification)
    return notification


def notify_check(check: Check, action: Action, now: datetime) -> Notification | None:
    project = check.project
    context = {
        "project": project,
        "check": check,
        "action": action.value,
        "health_url": health_url(project),
        "now": now,
        "cooldown_minutes": settings.MONITORING_ALERT_COOLDOWN_MINUTES,
    }
    subject = _SUBJECT[action].format(project=project.name, check=check.name)
    return create(
        project=project,
        kind=NotificationKind(action.value),
        # One message per check per action per minute, however often it is evaluated.
        dedupe_key=f"{action.value}:{check.id}:{now:%Y%m%d%H%M}",
        subject=subject,
        text=render_to_string("monitoring/email/check.txt", context),
        html=render_to_string("monitoring/email/check.html", context),
    )


def send(notification: Notification) -> None:
    """Send one notification to each recipient separately (no shared To: line)."""
    to = recipients(notification.organization_id)
    if not to:
        notification.last_error = "Nobody to notify: the organization has no owner or admin."
    else:
        messages = []
        for address in to:
            message = EmailMultiAlternatives(
                subject=f"[Commandr] {notification.subject}",
                body=notification.body_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[address],
            )
            if notification.body_html:
                message.attach_alternative(notification.body_html, "text/html")
            messages.append(message)
        with get_connection() as conn:
            conn.send_messages(messages)
        notification.last_error = ""
    notification.sent_at = timezone.now()
    notification.attempts += 1
    notification.save(update_fields=["sent_at", "attempts", "last_error"])
