"""Django SDK: `commandr-django` serves a signed status endpoint and pushes the rest.

One connection owns both halves: a polled status endpoint (checks, gauges,
KPIs) and an ingest key (traffic, errors, events). Data through either one
counts as the connection's first data.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework import serializers

from commandr.accounts.models import User
from commandr.ingest.models import KeyEnvironment
from commandr.integrations.models import Connection, ConnectionMode
from commandr.integrations.setup import Detail, FirstData, Reveal, SetupResult, Snippet
from commandr.monitoring.models import ErrorOccurrence, MetricSeries
from commandr.tenancy.models import Project

from ..common import INTERVAL_CHOICES, new_connection, public_url
from ..push_api.setup import create_key, key_details, revoke_key
from ..status_endpoint.setup import (
    DEFAULT_PATH,
    create_endpoint,
    endpoint_checks,
    endpoint_details,
    ensure_signing_secret,
    poll_now,
    remove_endpoint,
)

SLUG = "django_sdk"

INSTALL_SNIPPET = "pip install commandr-django"


def settings_snippet(*, project: Project, service: str) -> str:
    return f"""# settings.py
INSTALLED_APPS += ["commandr_django"]
MIDDLEWARE.insert(1, "commandr_django.middleware.TrafficMiddleware")
COMMANDR = {{
    "INGEST_KEY": env("COMMANDR_INGEST_KEY"),
    "SIGNING_SECRET": env("COMMANDR_SIGNING_SECRET"),
    "SERVICE": "{service}",
    "PROJECT": "prj_{project.id.hex}",
    "INGEST_URL": "{settings.INGEST_ORIGIN}",
}}

# urls.py
urlpatterns += [path("", include("commandr_django.urls"))]"""


class _Fields(serializers.Serializer[dict[str, Any]]):
    url = serializers.CharField(max_length=2000)
    interval = serializers.ChoiceField(choices=INTERVAL_CHOICES, default="300")
    environment = serializers.ChoiceField(
        choices=KeyEnvironment.choices, default=KeyEnvironment.LIVE
    )

    def validate_url(self, value: str) -> str:
        return public_url(value, allow_http=False)


class DjangoSdkSetup:
    slug = SLUG

    def validate(self, data: dict[str, Any], project: Project) -> dict[str, Any]:
        fields = _Fields(data=data)
        fields.is_valid(raise_exception=True)
        return dict(fields.validated_data)

    def create(self, *, project: Project, user: User, data: dict[str, Any]) -> SetupResult:
        url = data["url"]
        host = urlsplit(url).hostname or url
        connection = new_connection(
            project=project, user=user, slug=SLUG, mode=ConnectionMode.KEY, label=host
        )
        key = create_key(
            project=project,
            user=user,
            connection=connection,
            name=f"Django SDK: {host}",
            environment=data["environment"],
        )
        create_endpoint(project=project, connection=connection, url=url, interval=data["interval"])

        reveal = [Reveal("Ingest key", key, "secret")]
        notes = [
            "Set the ingest key in your app as COMMANDR_INGEST_KEY. It can only send "
            "data to this project. It is shown only now."
        ]
        secret = ensure_signing_secret(project, user)
        if secret is not None:
            reveal.append(Reveal("Signing secret", secret, "secret"))
            notes.append(
                "Set the signing secret as COMMANDR_SIGNING_SECRET. It is shown only now, "
                "and every status endpoint and SDK in this project uses the same one."
            )
        else:
            notes.append(
                "This project already has a signing secret; set that one as "
                "COMMANDR_SIGNING_SECRET."
            )
        if urlsplit(url).path != DEFAULT_PATH:
            notes.append(
                f"The SDK serves its status at {DEFAULT_PATH}; the address you entered "
                "uses another path, so make sure it reaches the SDK's view."
            )
        notes.append("We poll the address now; traffic and errors arrive within a minute.")
        return SetupResult(
            connection=connection,
            reveal=reveal,
            snippets=[
                Snippet("Install the package", INSTALL_SNIPPET),
                Snippet(
                    "Add it to your project",
                    settings_snippet(project=project, service=host),
                    "python",
                ),
            ],
            notes=notes,
        )

    def describe(self, connection: Connection) -> list[Detail]:
        return [*endpoint_details(connection), *key_details(connection)]

    def first_data(self, connection: Connection) -> FirstData:
        if connection.first_data_at is None:
            return FirstData(received_at=None)
        project_id = connection.project_id
        summary: list[Detail] = []
        counts = endpoint_checks(connection)
        if counts is not None:
            summary.append(Detail("Checks", f"{counts[0]} reported, {counts[1]} not ok"))
        summary += [
            Detail(
                "Metric series", str(MetricSeries.objects.filter(project_id=project_id).count())
            ),
            Detail("Errors", str(ErrorOccurrence.objects.filter(project_id=project_id).count())),
        ]
        return FirstData(received_at=connection.first_data_at, summary=summary)

    def disconnect(self, connection: Connection) -> None:
        revoke_key(connection)
        remove_endpoint(connection)

    def check_now(self, connection: Connection) -> bool:
        return poll_now(connection)
