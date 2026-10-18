import pytest
from django.db import connection
from rest_framework.test import APIClient

from tests.factories import MembershipFactory, OrganizationFactory, ProjectFactory, UserFactory


@pytest.fixture(autouse=True, scope="session")
def _refuse_superuser(django_db_setup: None, django_db_blocker: object) -> None:
    """RLS does not apply to superusers or BYPASSRLS roles, so every isolation
    test would pass for the wrong reason. Refuse to run at all."""
    with django_db_blocker.unblock(), connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        superuser, bypass = cursor.fetchone()
    if superuser or bypass:
        pytest.exit(
            "Tests must connect as a non-superuser without BYPASSRLS "
            "(use commandr_owner — see docs/development.md).",
            returncode=2,
        )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def org_a(db: None):  # type: ignore[no-untyped-def]
    return OrganizationFactory(name="Org A")


@pytest.fixture
def org_b(db: None):  # type: ignore[no-untyped-def]
    return OrganizationFactory(name="Org B")


@pytest.fixture
def owner_a(org_a):  # type: ignore[no-untyped-def]
    return MembershipFactory(organization=org_a, role="owner").user


@pytest.fixture
def owner_b(org_b):  # type: ignore[no-untyped-def]
    return MembershipFactory(organization=org_b, role="owner").user


@pytest.fixture
def project_a(org_a):  # type: ignore[no-untyped-def]
    return ProjectFactory(organization=org_a, name="Pantrini")


@pytest.fixture
def project_b(org_b):  # type: ignore[no-untyped-def]
    return ProjectFactory(organization=org_b, name="Other product")


@pytest.fixture
def user(db: None):  # type: ignore[no-untyped-def]
    return UserFactory()
