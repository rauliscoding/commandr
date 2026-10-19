"""Helpers shared by the connector setup handlers."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from rest_framework import serializers

from commandr.accounts.models import User
from commandr.core.safe_http import SafeHttpError, resolve_and_validate
from commandr.integrations.models import Connection, ConnectionMode, ConnectionStatus
from commandr.tenancy.models import Project

INTERVAL_CHOICES = (("300", "Every 5 minutes"), ("60", "Every minute"))


def new_connection(
    *, project: Project, user: User, slug: str, mode: str = ConnectionMode.NONE, label: str = ""
) -> Connection:
    return Connection.objects.create(
        project=project,
        connector_slug=slug,
        mode=mode,
        status=ConnectionStatus.PENDING,
        label=label[:120],
        created_by=user,
    )


def public_url(value: str, *, allow_http: bool) -> str:
    """A URL Commandr may fetch: checked at setup so the user hears now, not later.

    `safe_http` checks again on every fetch (DNS can change); this is for the
    message, not the protection.
    """
    value = value.strip()
    parts = urlsplit(value)
    schemes = {"https", "http"} if allow_http else {"https"}
    if parts.scheme not in schemes:
        raise serializers.ValidationError(
            "Use an https:// address." if not allow_http else "Use an http:// or https:// address."
        )
    if not parts.hostname:
        raise serializers.ValidationError("That address has no host name.")
    if parts.username or parts.password:
        raise serializers.ValidationError("Remove the user name and password from the address.")
    try:
        resolve_and_validate(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except SafeHttpError as exc:
        raise serializers.ValidationError(str(exc)) from exc
    return value


def when(value: datetime | None) -> str | None:
    """ISO time for the UI to format, or None ("—")."""
    return value.isoformat() if value else None


def every(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return "every day" if days == 1 else f"every {days} days"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "every hour" if hours == 1 else f"every {hours} hours"
    minutes = seconds // 60
    return "every minute" if minutes == 1 else f"every {minutes} minutes"
