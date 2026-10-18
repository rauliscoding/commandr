import pytest
from django.urls import reverse

from commandr.audit.models import AuditEvent
from commandr.tenancy.models import Membership, Role
from tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def projects_url(org_id: object) -> str:
    return reverse("projects", kwargs={"org_id": org_id})


def project_url(org_id: object, project_id: object) -> str:
    return reverse("project-detail", kwargs={"org_id": org_id, "project_id": project_id})


def test_me_requires_authentication(api) -> None:  # type: ignore[no-untyped-def]
    assert api.get(reverse("me")).status_code in (401, 403)


def test_onboarding_creates_org_owner_membership_and_project(api, user) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(user)
    response = api.post(
        reverse("organization-create"),
        {
            "name": "Pantrini",
            "country": "PT",
            "project_name": "Pantrini app",
            "project_kind": "mobile_app",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    org_id = response.data["organization"]["id"]

    me = api.get(reverse("me")).data
    assert [o["id"] for o in me["organizations"]] == [org_id]
    assert me["organizations"][0]["role"] == Role.OWNER
    assert [p["name"] for p in me["organizations"][0]["projects"]] == ["Pantrini app"]
    assert set(AuditEvent.objects.values_list("action", flat=True)) == {
        "organization.created",
        "project.created",
    }


def test_onboarding_validates_input(api, user) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(user)
    response = api.post(reverse("organization-create"), {"name": "x"}, format="json")
    assert response.status_code == 400
    assert "project_name" in response.data


def test_member_lists_only_their_projects(api, owner_a, project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_a)
    response = api.get(projects_url(project_a.organization_id))
    assert response.status_code == 200
    assert [p["id"] for p in response.data["results"]] == [str(project_a.id)]


def test_other_tenants_org_is_404_not_403(api, owner_b, project_a) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_b)
    assert api.get(projects_url(project_a.organization_id)).status_code == 404
    assert api.get(project_url(project_a.organization_id, project_a.id)).status_code == 404


def test_project_of_other_tenant_via_own_org_is_404(api, owner_b, org_b, project_a) -> None:  # type: ignore[no-untyped-def]
    """Own org in the URL, someone else's project id: scoped away, not leaked."""
    api.force_authenticate(owner_b)
    assert api.get(project_url(org_b.id, project_a.id)).status_code == 404


@pytest.mark.parametrize(
    ("role", "expected"),
    [(Role.VIEWER, 403), (Role.MEMBER, 403), (Role.ADMIN, 201), (Role.OWNER, 201)],
)
def test_only_admins_create_projects(api, org_a, role, expected) -> None:  # type: ignore[no-untyped-def]
    member = MembershipFactory(organization=org_a, role=role).user
    api.force_authenticate(member)
    response = api.post(
        projects_url(org_a.id), {"name": f"New {role}", "kind": "api"}, format="json"
    )
    assert response.status_code == expected


def test_viewers_can_read(api, org_a, project_a) -> None:  # type: ignore[no-untyped-def]
    viewer = MembershipFactory(organization=org_a, role=Role.VIEWER).user
    api.force_authenticate(viewer)
    assert api.get(project_url(org_a.id, project_a.id)).status_code == 200


def test_project_names_are_unique_per_org_only(api, owner_a, org_a, project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_a)
    dupe = api.post(projects_url(org_a.id), {"name": "pantrini"}, format="json")
    assert dupe.status_code == 400
    # Org B's project name is free in org A: uniqueness must not leak across tenants.
    other = api.post(projects_url(org_a.id), {"name": project_b.name}, format="json")
    assert other.status_code == 201


def test_deleting_a_project_is_audited(api, owner_a, org_a, project_a) -> None:  # type: ignore[no-untyped-def]
    api.force_authenticate(owner_a)
    assert api.delete(project_url(org_a.id, project_a.id)).status_code == 204
    event = AuditEvent.objects.get(action="project.deleted")
    assert event.organization_id == org_a.id
    assert event.target_id == str(project_a.id)


def test_membership_is_unique(org_a, owner_a) -> None:  # type: ignore[no-untyped-def]
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(organization=org_a, user=owner_a, role=Role.MEMBER)
