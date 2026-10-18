import pytest
from django.urls import reverse

from commandr.integrations.models import ConnectionStatus
from commandr.integrations.registry import Category, all_connectors
from tests.factories import ConnectionFactory, ProjectFactory

pytestmark = pytest.mark.django_db


def catalogue_url(project) -> str:  # type: ignore[no-untyped-def]
    return reverse(
        "catalogue", kwargs={"org_id": project.organization_id, "project_id": project.id}
    )


def test_catalogue_lists_every_registered_connector(api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_a)
    data = api.get(catalogue_url(project_a)).data
    assert {c["slug"] for c in data["connectors"]} == {m.slug for m in all_connectors()}
    assert [c["key"] for c in data["categories"]] == [c.value for c in Category]
    assert all(c["state"] == "not_connected" for c in data["connectors"])


def test_recommended_row_follows_project_kind(api, owner_a, org_a) -> None:  # type: ignore[no-untyped-def]
    mobile = ProjectFactory(organization=org_a, kind="mobile_app")
    api.force_authenticate(owner_a)
    data = api.get(catalogue_url(mobile)).data
    assert data["recommended"] == ["django_sdk", "heartbeat", "instagram", "tiktok"]
    flagged = [c["slug"] for c in data["connectors"] if c["recommended"]]
    assert set(flagged) == set(data["recommended"])


def test_connection_state_is_reflected_and_worst_state_wins(api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    ConnectionFactory(project=project_a, connector_slug="uptime_probe")
    ConnectionFactory(
        project=project_a, connector_slug="instagram", status=ConnectionStatus.CONNECTED
    )
    ConnectionFactory(
        project=project_a, connector_slug="instagram", status=ConnectionStatus.NEEDS_REAUTH
    )
    api.force_authenticate(owner_a)
    data = api.get(catalogue_url(project_a)).data
    states = {c["slug"]: c["state"] for c in data["connectors"]}
    assert states["uptime_probe"] == "connected"
    assert states["instagram"] == "needs_attention"
    assert data["connected_recommended"] == 1  # uptime_probe is recommended for web apps


def test_catalogue_does_not_count_other_tenants_connections(
    api, owner_a, project_a, project_b
) -> None:  # type: ignore[no-untyped-def]
    ConnectionFactory(project=project_b, connector_slug="resend")
    api.force_authenticate(owner_a)
    data = api.get(catalogue_url(project_a)).data
    assert {c["slug"]: c["state"] for c in data["connectors"]}["resend"] == "not_connected"


def test_catalogue_of_other_tenant_is_404(api, owner_b, project_a) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_b)
    assert api.get(catalogue_url(project_a)).status_code == 404


def test_catalogue_never_exposes_credentials(api, owner_a, project_a) -> None:  # type: ignore[no-untyped-def]
    conn = ConnectionFactory.build(project=project_a, organization=project_a.organization)
    from commandr.tenancy.context import tenant_context

    with tenant_context(project_a.organization_id):
        conn.set_credentials({"api_key": "re_" + "supersecretvalue1234567890"})
        conn.save()
    api.force_authenticate(owner_a)
    body = api.get(catalogue_url(project_a)).content.decode()
    assert "re_supersecretvalue" not in body
