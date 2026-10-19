"""Status endpoint: the customer's app serves a JSON document; we poll it, signed."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from commandr.accounts.models import User
from commandr.audit.services import record
from commandr.ingest.keys import generate_signing_secret
from commandr.ingest.models import SigningSecret
from commandr.integrations.models import Connection, ConnectionMode
from commandr.integrations.setup import Detail, FirstData, Reveal, SetupResult, Snippet
from commandr.monitoring.models import (
    Check,
    CheckSource,
    CheckStatus,
    MetricKind,
    MetricSeries,
    StatusEndpoint,
)
from commandr.tenancy.models import Project

from ..common import INTERVAL_CHOICES, every, new_connection, public_url, when

SLUG = "status_endpoint"
DEFAULT_PATH = "/.well-known/commandr/status"

VERIFY_SNIPPET = '''import hashlib, hmac, os, time

def commandr_request_is_valid(request) -> bool:
    """True if Commandr signed this request in the last 5 minutes."""
    secret = os.environ["COMMANDR_SIGNING_SECRET"].encode()
    try:
        parts = dict(p.split("=", 1) for p in request.headers["X-Commandr-Signature"].split(","))
        t = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - t) > 300:
        return False
    message = f"{t}.{request.method}.{request.path}".encode()   # path without the query string
    expected = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))'''

DOCUMENT_SNIPPET = """{
  "schema": "commandr.status/v1",
  "service": "my-app",
  "checks": [{"key": "database", "name": "Database", "status": "ok", "summary": "reachable"}],
  "gauges": [{"name": "queue.depth", "value": 3}],
  "kpis": [{"name": "user.total", "label": "Users", "value": 412, "unit": "count"}]
}"""


class _Fields(serializers.Serializer[dict[str, Any]]):
    url = serializers.CharField(max_length=2000)
    interval = serializers.ChoiceField(choices=INTERVAL_CHOICES, default="300")

    def validate_url(self, value: str) -> str:
        return public_url(value, allow_http=False)


def _endpoint(connection: Connection) -> StatusEndpoint | None:
    return StatusEndpoint.objects.filter(connection=connection).first()


# Shared with the Django SDK, whose connection is also a polled status endpoint.


def create_endpoint(*, project: Project, connection: Connection, url: str, interval: str) -> None:
    """Create the endpoint and poll it once the transaction commits."""
    from commandr.monitoring.tasks import enqueue_status_poll

    endpoint = StatusEndpoint.objects.create(
        project=project,
        connection=connection,
        url=url,
        interval_seconds=int(interval),
        next_run_at=timezone.now() + timedelta(seconds=int(interval)),
    )
    transaction.on_commit(lambda: enqueue_status_poll(endpoint))


def ensure_signing_secret(project: Project, user: User) -> str | None:
    """The project's signing secret if this call created it (show it once), else None."""
    if SigningSecret.objects.filter(project=project).exists():
        return None
    secret = generate_signing_secret()
    signing = SigningSecret(project=project)
    signing.set_secret(secret)
    signing.save()
    record("signing_secret.created", actor=user, organization=project.organization, target=signing)
    return secret


def endpoint_details(connection: Connection) -> list[Detail]:
    e = _endpoint(connection)
    if e is None:
        return []
    return [
        Detail("Address", e.url, "code"),
        Detail("Polled", every(e.interval_seconds)),
        Detail("Last poll", when(e.last_run_at), "time"),
        Detail("Last good answer", when(e.last_ok_at), "time"),
        Detail("Problem", e.last_error or None),
    ]


def endpoint_checks(connection: Connection) -> tuple[int, int] | None:
    """(checks reported, of which not ok), or None when there is no endpoint."""
    e = _endpoint(connection)
    if e is None:
        return None
    checks = Check.objects.filter(source=CheckSource.STATUS_ENDPOINT, source_id=e.id)
    return checks.count(), checks.exclude(status=CheckStatus.OK).count()


def remove_endpoint(connection: Connection) -> None:
    # The signing secret stays: it belongs to the project, not this endpoint.
    e = _endpoint(connection)
    if e is not None:
        Check.objects.filter(source=CheckSource.STATUS_ENDPOINT, source_id=e.id).delete()


def poll_now(connection: Connection) -> bool:
    from commandr.monitoring.tasks import enqueue_status_poll

    e = _endpoint(connection)
    if e is None:
        return False
    transaction.on_commit(lambda: enqueue_status_poll(e))
    return True


class StatusEndpointSetup:
    slug = SLUG

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        fields = _Fields(data=data)
        fields.is_valid(raise_exception=True)
        return dict(fields.validated_data)

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        url = data["url"]
        connection = new_connection(
            project=project,
            user=user,
            slug=SLUG,
            mode=ConnectionMode.KEY,
            label=urlsplit(url).hostname or url,
        )
        create_endpoint(project=project, connection=connection, url=url, interval=data["interval"])

        reveal: list[Reveal] = []
        notes = ["We send a signed test request now and show the result here."]
        secret = ensure_signing_secret(project, user)
        if secret is not None:
            reveal.append(Reveal("Signing secret", secret, "secret"))
            notes.append(
                "Set it in your app as COMMANDR_SIGNING_SECRET. It is shown only now, and "
                "every status endpoint and SDK in this project uses the same one."
            )
        else:
            notes.append("This project already has a signing secret; your app uses that one.")

        if urlsplit(url).path in ("", "/"):
            notes.append(f"The usual path is {DEFAULT_PATH}.")
        return SetupResult(
            connection=connection,
            reveal=reveal,
            snippets=[
                Snippet("Check our signature before answering (Python)", VERIFY_SNIPPET, "python"),
                Snippet("The smallest valid status document", DOCUMENT_SNIPPET, "json"),
            ],
            notes=notes,
        )

    def describe(self, connection: Connection) -> list[Detail]:
        return endpoint_details(connection)

    def first_data(self, connection: Connection) -> FirstData:
        e = _endpoint(connection)
        if e is None or connection.first_data_at is None:
            return FirstData(received_at=None)
        checks = Check.objects.filter(source=CheckSource.STATUS_ENDPOINT, source_id=e.id)
        failing = checks.exclude(status=CheckStatus.OK).count()
        project_series = MetricSeries.objects.filter(project_id=e.project_id)
        return FirstData(
            received_at=connection.first_data_at,
            summary=[
                Detail("Checks", f"{checks.count()} reported, {failing} not ok"),
                Detail("Gauges", str(project_series.filter(kind=MetricKind.GAUGE).count())),
                Detail("KPIs", str(project_series.filter(kind=MetricKind.KPI).count())),
            ],
        )

    def disconnect(self, connection: Connection) -> None:
        remove_endpoint(connection)

    def check_now(self, connection: Connection) -> bool:
        return poll_now(connection)
