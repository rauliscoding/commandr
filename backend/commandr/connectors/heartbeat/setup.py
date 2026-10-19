"""Heartbeat: a job calls its URL after each run; silence past the grace is a failure."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from commandr.accounts.models import User
from commandr.ingest import heartbeats as hb_state
from commandr.ingest import lookup
from commandr.ingest.keys import digest, generate_heartbeat_token
from commandr.ingest.models import CredentialKind, Heartbeat
from commandr.integrations.models import Connection, ConnectionMode
from commandr.integrations.setup import Detail, FirstData, Reveal, SetupResult, Snippet
from commandr.monitoring.models import Check, CheckSource
from commandr.tenancy.models import Project

from ..common import every, new_connection, when

SLUG = "heartbeat"

PERIOD_CHOICES = (
    ("300", "Every 5 minutes"),
    ("900", "Every 15 minutes"),
    ("3600", "Every hour"),
    ("21600", "Every 6 hours"),
    ("86400", "Every day"),
    ("604800", "Every week"),
)
GRACE_CHOICES = (
    ("300", "5 minutes"),
    ("900", "15 minutes"),
    ("3600", "1 hour"),
    ("21600", "6 hours"),
)


class _Fields(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=120)
    period = serializers.ChoiceField(choices=PERIOD_CHOICES, default="86400")
    grace = serializers.ChoiceField(choices=GRACE_CHOICES, default="3600")

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if Heartbeat.objects.filter(project=self.context["project"], name__iexact=value).exists():
            raise serializers.ValidationError(
                "This project already has a heartbeat with that name."
            )
        return value


def _heartbeat(connection: Connection) -> Heartbeat | None:
    return Heartbeat.objects.filter(connection=connection).first()


class HeartbeatSetup:
    slug = SLUG

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        fields = _Fields(data=data, context={"project": project})
        fields.is_valid(raise_exception=True)
        return dict(fields.validated_data)

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        token = generate_heartbeat_token()
        connection = new_connection(
            project=project, user=user, slug=SLUG, mode=ConnectionMode.KEY, label=data["name"]
        )
        hb = Heartbeat.objects.create(
            project=project,
            connection=connection,
            name=data["name"],
            period_seconds=int(data["period"]),
            grace_seconds=int(data["grace"]),
            token_hash=digest(token),
        )
        lookup.add(
            credential_digest=hb.token_hash,
            kind=CredentialKind.HEARTBEAT,
            organization_id=project.organization_id,
            target_id=hb.id,
        )
        hb.project = project
        hb_state.refresh_check(hb, timezone.now())  # "waiting for the first ping": unknown

        url = f"{settings.INGEST_ORIGIN}/v1/heartbeat/{token}"
        return SetupResult(
            connection=connection,
            reveal=[Reveal("Heartbeat URL", url, "url")],
            snippets=[
                Snippet(
                    "At the end of the job, when it succeeded", f"curl -fsS -m 10 --retry 3 {url}"
                ),
                Snippet(
                    "Optional: at the start, to measure how long it takes",
                    f"curl -fsS -m 10 --retry 3 {url}/start",
                ),
                Snippet(
                    "Optional: when it fails, with a short message",
                    f'curl -fsS -m 10 --retry 3 --data-raw "Backup failed: disk full" {url}/fail',
                ),
            ],
            notes=[
                "The URL is the credential: anyone with it can report this job. "
                "It is shown only now; if you lose it, remove this heartbeat and add it again."
            ],
        )

    def describe(self, connection: Connection) -> list[Detail]:
        hb = _heartbeat(connection)
        if hb is None:
            return []
        return [
            Detail(
                "Expected",
                f"{every(hb.period_seconds)}, alert after {hb.grace_seconds // 60} min late",
            ),
            Detail("Last ping", when(hb.last_ping_at), "time"),
            Detail("Last failure", when(hb.last_fail_at), "time"),
            Detail(
                "Last run took",
                f"{hb.last_duration_ms / 1000:.1f} s" if hb.last_duration_ms is not None else None,
            ),
        ]

    def first_data(self, connection: Connection) -> FirstData:
        hb = _heartbeat(connection)
        summary = []
        if hb is not None:
            result = hb_state.status(hb, timezone.now())
            summary = [Detail("Status", result.summary), *self.describe(connection)[1:]]
        return FirstData(received_at=connection.first_data_at, summary=summary)

    def disconnect(self, connection: Connection) -> None:
        hb = _heartbeat(connection)
        if hb is not None:
            lookup.remove(hb.token_hash)  # the URL stops working immediately
            Check.objects.filter(source=CheckSource.HEARTBEAT, source_id=hb.id).delete()

    def check_now(self, connection: Connection) -> bool:
        return False  # the job calls us; there is nothing to fetch
