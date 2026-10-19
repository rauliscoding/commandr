"""Uptime probe: we request a URL every minute or five, from Commandr's network."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from commandr.accounts.models import User
from commandr.integrations.models import Connection
from commandr.integrations.setup import Detail, FirstData, SetupResult
from commandr.monitoring.models import Check, CheckSource, UptimeMonitor
from commandr.tenancy.models import Project

from ..common import INTERVAL_CHOICES, every, new_connection, public_url, when

SLUG = "uptime_probe"


class _Fields(serializers.Serializer[dict[str, Any]]):
    url = serializers.CharField(max_length=2000)
    interval = serializers.ChoiceField(choices=INTERVAL_CHOICES, default="300")

    def validate_url(self, value: str) -> str:
        # http:// is allowed for uptime only (security.md); the UI flags it.
        return public_url(value, allow_http=True)


def _monitor(connection: Connection) -> UptimeMonitor | None:
    return UptimeMonitor.objects.filter(connection=connection).first()


class UptimeProbeSetup:
    slug = SLUG

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        fields = _Fields(data=data)
        fields.is_valid(raise_exception=True)
        return dict(fields.validated_data)

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        from commandr.monitoring.tasks import enqueue_uptime_probe

        url = data["url"]
        connection = new_connection(
            project=project, user=user, slug=SLUG, label=urlsplit(url).hostname or url
        )
        monitor = UptimeMonitor.objects.create(
            project=project,
            connection=connection,
            url=url,
            interval_seconds=int(data["interval"]),
            # The first scheduled run comes one interval later: we probe once now.
            next_run_at=timezone.now() + timedelta(seconds=int(data["interval"])),
        )
        transaction.on_commit(lambda: enqueue_uptime_probe(monitor))
        notes = ["We are checking it now. The result appears here in a few seconds."]
        if url.startswith("http://"):
            notes.append(
                "This address uses http://, so the check cannot confirm your TLS "
                "certificate or that traffic is encrypted."
            )
        return SetupResult(connection=connection, notes=notes)

    def describe(self, connection: Connection) -> list[Detail]:
        m = _monitor(connection)
        if m is None:
            return []
        if m.last_error:
            last = m.last_error
        elif m.last_status_code is not None:
            last = f"HTTP {m.last_status_code} in {m.last_response_ms} ms"
        else:
            last = None
        return [
            Detail("Address", m.url, "code"),
            Detail("Checked", every(m.interval_seconds)),
            Detail("Last check", when(m.last_run_at), "time"),
            Detail("Last result", last),
            Detail("TLS certificate expires", when(m.tls_expires_at), "time"),
        ]

    def first_data(self, connection: Connection) -> FirstData:
        m = _monitor(connection)
        summary = self.describe(connection)[3:] if m else []
        return FirstData(received_at=connection.first_data_at, summary=summary)

    def disconnect(self, connection: Connection) -> None:
        m = _monitor(connection)
        if m is not None:
            Check.objects.filter(source=CheckSource.UPTIME, source_id=m.id).delete()

    def check_now(self, connection: Connection) -> bool:
        from commandr.monitoring.tasks import enqueue_uptime_probe

        m = _monitor(connection)
        if m is None:
            return False
        transaction.on_commit(lambda: enqueue_uptime_probe(m))
        return True
