"""The Django SDK connector: one connection, a polled status endpoint and an ingest key."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse

from commandr.audit.models import AuditEvent
from commandr.ingest import stream
from commandr.ingest.models import CredentialLookup, IngestKey, SigningSecret
from commandr.integrations.models import Connection, ConnectionStatus
from commandr.integrations.setup import get_setup
from commandr.monitoring import signing
from commandr.monitoring.models import Check, CheckStatus, MetricPoint, StatusEndpoint
from commandr.tenancy.context import tenant_context
from tests.factories import setup_connection

pytestmark = pytest.mark.django_db

URL = "https://api.pantrini.test/.well-known/commandr/status"

# What commandr-django answers (sdks/python/commandr-django, validated there
# against the same contract).
SDK_DOCUMENT = {
    "schema": "commandr.status/v1",
    "service": "pantrini-api",
    "generated_at": "2026-10-19T06:00:00Z",
    "checks": [
        {"key": "database", "name": "PostgreSQL", "status": "ok", "summary": "reachable"},
        {"key": "cache", "name": "Cache", "status": "ok", "summary": "reachable"},
        {"key": "celery", "name": "Celery workers", "status": "fail", "summary": "no worker"},
        {
            "key": "disk",
            "name": "Disk",
            "status": "ok",
            "summary": "41.0 / 100 GB",
            "value": 0.41,
            "unit": "ratio",
        },
    ],
    "gauges": [{"name": "system.cpu.load_per_core", "value": 0.16}],
    "kpis": [{"name": "user.total", "label": "Users", "value": 412, "unit": "count"}],
}


def url(name: str, project, **extra) -> str:  # type: ignore[no-untyped-def]
    return reverse(
        name, kwargs={"org_id": project.organization_id, "project_id": project.id, **extra}
    )


@pytest.fixture
def sdk(project_a, owner_a, http, django_capture_on_commit_callbacks):  # type: ignore[no-untyped-def]
    """Set up through the real handler; the app answers like the SDK, checking our signature."""
    box: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        now = int(datetime.now(UTC).timestamp())
        header = request.headers["x-commandr-signature"]
        if not signing.verify(box["secret"], header, "GET", request.url.path, now):
            return httpx.Response(401)
        return httpx.Response(200, json=SDK_DOCUMENT)

    http.handler = handler
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        result = setup_connection(project_a, owner_a, "django_sdk", url=URL, interval="60")
    box["secret"] = {r.label: r.value for r in result.reveal}["Signing secret"]
    for callback in callbacks:
        callback()
    return result


def test_setup_reveals_a_key_and_the_secret_and_polls_signed(sdk, project_a, http) -> None:  # type: ignore[no-untyped-def]
    reveal = {r.label: r.value for r in sdk.reveal}
    assert reveal["Ingest key"].startswith("cmdr_ingest_live_")
    assert reveal["Signing secret"].startswith("cmdr_sign_")
    code = "\n".join(s.code for s in sdk.snippets)
    assert "pip install commandr-django" in code
    assert f'"PROJECT": "prj_{project_a.id.hex}"' in code
    assert f'"INGEST_URL": "{settings.INGEST_ORIGIN}"' in code
    assert reveal["Ingest key"] not in code  # the settings read it from the environment

    request = http.requests[0]
    assert request.url.path == "/.well-known/commandr/status"
    assert request.headers["x-commandr-project"] == f"prj_{project_a.id.hex}"
    with tenant_context(project_a.organization_id):
        connection = Connection.objects.get()
        assert connection.connector_slug == "django_sdk"
        assert connection.status == ConnectionStatus.CONNECTED
        assert IngestKey.objects.get().connection == connection
        assert StatusEndpoint.objects.get().connection == connection
        checks = {c.key: c.status for c in Check.objects.all()}
        assert checks["celery"] == CheckStatus.FAIL
        assert checks["commandr.reachability"] == CheckStatus.OK
        first = get_setup("django_sdk").first_data(connection)  # type: ignore[union-attr]
    summary = {d.label: d.value for d in first.summary}
    assert summary["Checks"] == "5 reported, 1 not ok"  # the app's 4 and reachability


def test_a_second_sdk_reuses_the_projects_signing_secret(project_a, owner_a, public_dns) -> None:  # type: ignore[no-untyped-def]
    setup_connection(project_a, owner_a, "status_endpoint", url=URL, interval="300")
    result = setup_connection(
        project_a, owner_a, "django_sdk", url="https://b.pantrini.test" + URL[24:]
    )
    assert [r.label for r in result.reveal] == ["Ingest key"]
    assert any("already has a signing secret" in n for n in result.notes)
    with tenant_context(project_a.organization_id):
        assert SigningSecret.objects.count() == 1


def test_another_path_gets_a_note(project_a, owner_a, public_dns) -> None:  # type: ignore[no-untyped-def]
    result = setup_connection(
        project_a, owner_a, "django_sdk", url="https://api.pantrini.test/status"
    )
    assert any("/.well-known/commandr/status" in n for n in result.notes)


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"url": "http://api.pantrini.test/s"}, "url"),
        ({"url": "https://local.test/s"}, "url"),
        ({"url": URL, "interval": "7"}, "interval"),
        ({"url": URL, "environment": "staging"}, "environment"),
    ],
)
def test_fields_are_validated(fresh_api, owner_a, project_a, public_dns, fields, error) -> None:  # type: ignore[no-untyped-def]
    public_dns["local.test"] = ["127.0.0.1"]
    response = fresh_api(owner_a).post(
        url("connections", project_a), {"connector": "django_sdk", "fields": fields}, format="json"
    )
    assert response.status_code == 400
    assert error in response.data


def test_listing_describes_both_halves_without_secrets(
    fresh_api, owner_a, project_a, public_dns
) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    created = api.post(
        url("connections", project_a),
        {"connector": "django_sdk", "fields": {"url": URL, "environment": "test"}},
        format="json",
    )
    assert created.status_code == 201, created.data
    listing = api.get(url("connections", project_a))
    body = listing.content.decode()
    for revealed in created.data["reveal"]:
        assert revealed["value"] not in body
    details = {d["label"]: d["value"] for d in listing.data["results"][0]["details"]}
    assert details["Address"] == URL
    assert details["Key"].startswith("cmdr_ingest_test_…")
    assert details["Last poll"] is None  # not polled yet: unknown, not zero


def test_pushing_with_the_sdk_key_is_first_data(
    project_a, owner_a, fake_stream, public_dns
) -> None:  # type: ignore[no-untyped-def]
    result = setup_connection(project_a, owner_a, "django_sdk", url=URL)
    key = {r.label: r.value for r in result.reveal}["Ingest key"]
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    body = {
        "schema": "commandr.ingest/v1",
        "resource": {"service": "pantrini-api"},
        "metrics": [
            {
                "name": "http.server.requests",
                "type": "counter",
                "value": 12,
                "ts": now,
                "interval_s": 60,
                "attrs": {"route": "api/items/{pk}/", "status_class": "2xx"},
            }
        ],
    }
    with override_settings(ROOT_URLCONF="config.urls_ingest"):
        response = Client().post(
            "/v1/ingest",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {key}",
        )
    assert response.status_code == 202, response.content
    assert stream.drain_once(fake_stream, "test") == 1
    with tenant_context(project_a.organization_id):
        connection = Connection.objects.get()
        assert connection.first_data_at is not None
        assert connection.status == ConnectionStatus.CONNECTED


def test_counters_from_two_workers_both_count(project_a, owner_a, fake_stream, public_dns) -> None:  # type: ignore[no-untyped-def]
    """Points are de-duplicated by (series, ts): the SDK gives each process its own
    sub-second offset, so two workers' counts for the same minute are both kept."""
    result = setup_connection(project_a, owner_a, "django_sdk", url=URL)
    key = {r.label: r.value for r in result.reveal}["Ingest key"]
    minute = (datetime.now(UTC) - timedelta(minutes=1)).replace(second=0, microsecond=0)

    def counter(microsecond: int, value: int) -> dict[str, object]:
        return {
            "name": "http.server.requests",
            "type": "counter",
            "value": value,
            "ts": minute.replace(microsecond=microsecond).isoformat(),
            "interval_s": 60,
            "attrs": {"route": "api/items/{pk}/", "status_class": "2xx"},
        }

    metrics = [counter(123456, 5), counter(654321, 7), counter(654321, 7)]  # last: a resend
    with override_settings(ROOT_URLCONF="config.urls_ingest"):
        for metric in metrics:
            Client().post(
                "/v1/ingest",
                data=json.dumps({"schema": "commandr.ingest/v1", "metrics": [metric]}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {key}",
            )
    stream.drain_once(fake_stream, "test")
    with tenant_context(project_a.organization_id):
        values = sorted(
            MetricPoint.objects.filter(series__name="http.server.requests").values_list(
                "value", flat=True
            )
        )
    assert values == [5, 7]


def test_removing_revokes_the_key_and_the_checks(fresh_api, owner_a, project_a, sdk) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    connection_id = sdk.connection.id
    response = api.delete(url("connection-detail", project_a, connection_id=connection_id))
    assert response.status_code == 204
    assert CredentialLookup.objects.count() == 0
    with tenant_context(project_a.organization_id):
        assert Connection.objects.count() == 0
        assert IngestKey.objects.count() == 0
        assert StatusEndpoint.objects.count() == 0
        assert Check.objects.count() == 0
        assert SigningSecret.objects.count() == 1  # the project's, not this connection's
    assert AuditEvent.objects.filter(action="ingest_key.revoked").exists()


def test_check_now_polls_again(fresh_api, owner_a, project_a, sdk, http) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    response = api.post(url("connection-check-now", project_a, connection_id=sdk.connection.id))
    assert response.status_code == 202
    assert http.requests[-1].headers["host"] == urlsplit(URL).hostname
