"""The generic setup API the wizard drives, the Health API and alert rules."""

from urllib.parse import urlsplit

import pytest
from django.test import Client
from django.urls import reverse

from commandr.audit.models import AuditEvent
from commandr.ingest.models import CredentialLookup, IngestKey
from commandr.integrations.models import Connection
from commandr.monitoring.models import Check, CheckStatus
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Role
from tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def url(name: str, project, **extra) -> str:  # type: ignore[no-untyped-def]
    return reverse(
        name, kwargs={"org_id": project.organization_id, "project_id": project.id, **extra}
    )


def create(api, project, connector, **fields):  # type: ignore[no-untyped-def]
    return api.post(
        url("connections", project), {"connector": connector, "fields": fields}, format="json"
    )


# --- Permissions -----------------------------------------------------------------


def test_unauthenticated_is_refused(api, project_a) -> None:  # type: ignore[no-untyped-def]
    assert create(api, project_a, "push_api", name="x").status_code in (401, 403)
    assert api.get(url("health", project_a)).status_code in (401, 403)


def test_connecting_needs_a_recent_sign_in(api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_a)  # authenticated, but no recent password entry
    response = create(api, project_a, "push_api", name="Prod", environment="live")
    assert response.status_code == 401
    assert response.data["code"] == "reauthentication_required"


@pytest.mark.parametrize("role", [Role.VIEWER, Role.MEMBER])
def test_only_admins_connect(fresh_api, org_a, project_a, role) -> None:  # type: ignore[no-untyped-def]
    user = MembershipFactory(organization=org_a, role=role).user
    api = fresh_api(user)
    assert create(api, project_a, "push_api", name="Prod").status_code == 403
    assert api.get(url("connections", project_a)).status_code == 200
    assert api.get(url("health", project_a)).status_code == 200


def test_other_tenant_gets_404_everywhere(fresh_api, owner_a, owner_b, project_a) -> None:  # type: ignore[no-untyped-def]
    conn_id = create(fresh_api(owner_a), project_a, "push_api", name="Prod").data["connection"][
        "id"
    ]
    api = fresh_api(owner_b)
    for name, extra in [
        ("connections", {}),
        ("health", {}),
        ("alert-rules", {}),
        ("connection-detail", {"connection_id": conn_id}),
        ("connection-first-data", {"connection_id": conn_id}),
    ]:
        assert api.get(url(name, project_a, **extra)).status_code == 404, name
    assert api.delete(url("connection-detail", project_a, connection_id=conn_id)).status_code == 404


# --- Setup per connector ----------------------------------------------------------


def test_push_api_reveals_the_key_once(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    response = create(api, project_a, "push_api", name="Prod", environment="test")
    assert response.status_code == 201, response.data
    secret = response.data["reveal"][0]["value"]
    assert secret.startswith("cmdr_ingest_test_")
    assert "v1/ingest" in response.data["snippets"][0]["code"]
    listing = api.get(url("connections", project_a))
    assert secret not in listing.content.decode()
    details = {d["label"]: d["value"] for d in listing.data["results"][0]["details"]}
    assert details["Key"].endswith(secret[-4:])
    assert details["Last used"] is None  # unknown, not zero
    assert AuditEvent.objects.filter(action="ingest_key.created").count() == 1
    assert AuditEvent.objects.filter(action="connection.created").count() == 1


def test_heartbeat_setup_waits_for_the_first_ping(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    response = create(api, project_a, "heartbeat", name="Backup", period="86400", grace="3600")
    assert response.status_code == 201, response.data
    ping_url = response.data["reveal"][0]["value"]
    first = url("connection-first-data", project_a, connection_id=response.data["connection"]["id"])
    assert api.get(first).data["state"] == "waiting"

    from django.test import override_settings

    with override_settings(ROOT_URLCONF="config.urls_ingest"):
        assert Client().get(urlsplit(ping_url).path).status_code == 204
    data = api.get(first).data
    assert data["state"] == "received"
    assert data["summary"][0]["label"] == "Status"


def test_heartbeat_names_are_unique_per_project(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    create(api, project_a, "heartbeat", name="Backup")
    response = create(api, project_a, "heartbeat", name="backup")
    assert response.status_code == 400
    assert "name" in response.data


def test_uptime_setup_validates_the_address(fresh_api, owner_a, project_a, public_dns) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    public_dns["local.test"] = ["127.0.0.1"]
    assert "url" in create(api, project_a, "uptime_probe", url="https://local.test/").data
    assert "url" in create(api, project_a, "uptime_probe", url="ftp://x.test/").data
    assert (
        "interval"
        in create(api, project_a, "uptime_probe", url="https://ok.test/", interval="7").data
    )
    ok = create(api, project_a, "uptime_probe", url="http://ok.test/", interval="60")
    assert ok.status_code == 201
    assert any("http://" in note for note in ok.data["notes"])


@pytest.mark.parametrize("connector", ["instagram", "nope", None])
def test_unavailable_connectors_cannot_be_created(fresh_api, owner_a, project_a, connector) -> None:  # type: ignore[no-untyped-def]
    response = create(fresh_api(owner_a), project_a, connector)
    assert response.status_code == 400
    assert "connector" in response.data


def test_removing_a_push_connection_revokes_its_key(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    data = create(api, project_a, "push_api", name="Prod").data
    secret = data["reveal"][0]["value"]
    assert (
        api.delete(
            url("connection-detail", project_a, connection_id=data["connection"]["id"])
        ).status_code
        == 204
    )
    assert CredentialLookup.objects.count() == 0
    with tenant_context(project_a.organization_id):
        assert Connection.objects.count() == 0
        assert IngestKey.objects.count() == 0
    assert AuditEvent.objects.filter(action="ingest_key.revoked").exists()
    assert AuditEvent.objects.filter(action="connection.removed").exists()

    from django.test import override_settings

    with override_settings(ROOT_URLCONF="config.urls_ingest"):
        response = Client().post(
            "/v1/ingest",
            data='{"schema": "commandr.ingest/v1"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {secret}",
        )
    assert response.status_code == 401


def test_check_now_only_for_polled_connectors(fresh_api, owner_a, project_a, http) -> None:  # type: ignore[no-untyped-def]
    api = fresh_api(owner_a)
    push = create(api, project_a, "push_api", name="Prod").data["connection"]["id"]
    probe = create(api, project_a, "uptime_probe", url="https://ok.test/").data["connection"]["id"]
    assert api.post(url("connection-check-now", project_a, connection_id=push)).status_code == 400
    assert api.post(url("connection-check-now", project_a, connection_id=probe)).status_code == 202


def test_catalogue_offers_the_four_health_connectors_with_their_fields(
    fresh_api, owner_a, project_a
) -> None:  # type: ignore[no-untyped-def]
    data = fresh_api(owner_a).get(url("catalogue", project_a)).data
    available = {c["slug"]: c for c in data["connectors"] if c["availability"] == "available"}
    assert set(available) == {"uptime_probe", "heartbeat", "status_endpoint", "push_api"}
    fields = {f["name"]: f for f in available["heartbeat"]["fields"]}
    assert fields["period"]["kind"] == "select"
    assert {"value": "86400", "label": "Every day"} in fields["period"]["options"]


# --- Health ----------------------------------------------------------------------------


def test_health_starts_with_nothing_checked(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    data = fresh_api(owner_a).get(url("health", project_a)).data
    assert data["verdict"]["state"] == "nothing_checked"
    assert data["checks"] == data["kpis"] == data["heartbeats"] == []


def test_health_shows_unknown_kpis_as_null(fresh_api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from commandr.monitoring.write import MetricIn, write_metrics

    with tenant_context(project_a.organization_id):
        write_metrics(
            project_a.id,
            [MetricIn("revenue.mrr", "kpi", None, datetime.now(UTC), label="MRR")],
        )
    kpis = fresh_api(owner_a).get(url("health", project_a)).data["kpis"]
    assert kpis == [
        {
            "name": "revenue.mrr",
            "label": "MRR",
            "unit": "",
            "value": None,
            "as_of": kpis[0]["as_of"],
        }
    ]


# --- Alert rules --------------------------------------------------------------------------


def test_alert_rules(fresh_api, owner_a, org_a, project_a) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from commandr.monitoring.write import MetricIn, write_metrics

    api = fresh_api(owner_a)
    rules = url("alert-rules", project_a)
    bad = api.post(
        rules, {"name": "Queue", "metric": "queue.depth", "kind": "threshold"}, format="json"
    )
    assert bad.status_code == 400
    assert {"comparator", "threshold"} <= set(bad.data)

    member = fresh_api(MembershipFactory(organization=org_a, role=Role.MEMBER).user)
    body = {
        "name": "Queue backed up",
        "metric": "queue.depth",
        "kind": "threshold",
        "comparator": "gt",
        "threshold": 100,
        "window_seconds": 600,
    }
    assert member.post(rules, body, format="json").status_code == 403

    api = fresh_api(owner_a)
    created = api.post(rules, body, format="json")
    assert created.status_code == 201, created.data
    with tenant_context(project_a.organization_id):
        assert Check.objects.get(source="rule").status == CheckStatus.UNKNOWN  # no data yet
        write_metrics(project_a.id, [MetricIn("queue.depth", "gauge", 250, datetime.now(UTC))])
        from commandr.monitoring import rules as rules_mod

        rules_mod.evaluate_for_metrics(project_a, {"queue.depth"}, datetime.now(UTC))
        check = Check.objects.get(source="rule")
        assert check.status == CheckStatus.FAIL
        assert "250" in check.summary

    detail = url("alert-rule-detail", project_a, rule_id=created.data["id"])
    assert api.delete(detail).status_code == 204
    with tenant_context(project_a.organization_id):
        assert not Check.objects.filter(source="rule").exists()
