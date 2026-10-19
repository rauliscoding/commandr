"""Push API: the customer's code POSTs batches to /v1/ingest with an ingest key."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from commandr.accounts.models import User
from commandr.audit.services import record
from commandr.ingest import lookup
from commandr.ingest.keys import digest, generate_ingest_key
from commandr.ingest.models import CredentialKind, IngestKey, KeyEnvironment
from commandr.integrations.models import Connection, ConnectionMode
from commandr.integrations.setup import Detail, FirstData, Reveal, SetupResult, Snippet
from commandr.monitoring.models import ErrorOccurrence, Event, MetricSeries
from commandr.tenancy.models import Project

from ..common import new_connection, when

SLUG = "push_api"


class _Fields(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(max_length=120)
    environment = serializers.ChoiceField(
        choices=KeyEnvironment.choices, default=KeyEnvironment.LIVE
    )


def _key(connection: Connection) -> IngestKey | None:
    return IngestKey.objects.filter(connection=connection).first()


class PushApiSetup:
    slug = SLUG

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        fields = _Fields(data=data)
        fields.is_valid(raise_exception=True)
        return dict(fields.validated_data)

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        secret = generate_ingest_key(data["environment"])
        connection = new_connection(
            project=project, user=user, slug=SLUG, mode=ConnectionMode.KEY, label=data["name"]
        )
        key = IngestKey.objects.create(
            project=project,
            connection=connection,
            name=data["name"].strip(),
            environment=data["environment"],
            key_hash=digest(secret),
            last4=secret[-4:],
            created_by=user,
        )
        lookup.add(
            credential_digest=key.key_hash,
            kind=CredentialKind.INGEST_KEY,
            organization_id=project.organization_id,
            target_id=key.id,
        )
        record(
            "ingest_key.created",
            actor=user,
            organization=project.organization,
            target=key,
            metadata={"name": key.name, "environment": key.environment, "last4": key.last4},
        )
        example = (
            f"curl -sS {settings.INGEST_ORIGIN}/v1/ingest \\\n"
            '  -H "Authorization: Bearer $COMMANDR_INGEST_KEY" \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"schema": "commandr.ingest/v1", "metrics": '
            '[{"name": "queue.depth", "type": "gauge", "value": 3}]}\''
        )
        return SetupResult(
            connection=connection,
            reveal=[Reveal("Ingest key", secret, "secret")],
            snippets=[Snippet("Send a test batch", example)],
            notes=[
                "Keep the key server-side, for example as COMMANDR_INGEST_KEY. It can "
                "only send data to this project. It is shown only now."
            ],
        )

    def describe(self, connection: Connection) -> list[Detail]:
        key = _key(connection)
        if key is None:
            return []
        return [
            Detail("Key", f"cmdr_ingest_{key.environment}_…{key.last4}", "code"),
            Detail("Created", when(key.created_at), "time"),
            Detail("Last used", when(key.last_used_at), "time"),
            Detail("Last used from", key.last_used_ip),
        ]

    def first_data(self, connection: Connection) -> FirstData:
        key = _key(connection)
        if key is None or connection.first_data_at is None:
            return FirstData(received_at=None)
        project_id = key.project_id
        return FirstData(
            received_at=connection.first_data_at,
            summary=[
                Detail(
                    "Metric series", str(MetricSeries.objects.filter(project_id=project_id).count())
                ),
                Detail("Events", str(Event.objects.filter(project_id=project_id).count())),
                Detail(
                    "Errors", str(ErrorOccurrence.objects.filter(project_id=project_id).count())
                ),
            ],
        )

    def disconnect(self, connection: Connection) -> None:
        key = _key(connection)
        if key is None:
            return
        lookup.remove(key.key_hash)  # refused from the next request on
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        record(
            "ingest_key.revoked",
            actor=None,
            organization=connection.project.organization,
            target=key,
            metadata={"name": key.name, "last4": key.last4},
        )

    def check_now(self, connection: Connection) -> bool:
        return False
