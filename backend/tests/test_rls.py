"""Row-level security: the database layer of tenant isolation (ADR 0002).

Each test here bypasses the application's scoping on purpose (raw SQL, the
unscoped manager) to prove the database alone still refuses cross-tenant access.
"""

import pytest
from django.apps import apps
from django.db import ProgrammingError, connection, transaction

from commandr.tenancy.context import TenantContextError, tenant_context
from commandr.tenancy.models import Project, TenantOwned
from tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db


def _raw_project_ids() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id::text FROM tenancy_project")
        return {row[0] for row in cursor.fetchall()}


def test_every_tenant_table_has_rls_enabled_and_forced() -> None:
    tenant_models = [
        m for m in apps.get_models() if issubclass(m, TenantOwned) and not m._meta.abstract
    ]
    assert tenant_models, "expected at least one tenant model"
    with connection.cursor() as cursor:
        for model in tenant_models:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
                [model._meta.db_table],
            )
            enabled, forced = cursor.fetchone()
            assert enabled, f"{model._meta.db_table}: RLS not enabled — add EnableRowLevelSecurity"
            assert forced, f"{model._meta.db_table}: RLS not forced for the table owner"


def test_raw_sql_sees_only_the_active_tenant(project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(project_a.organization_id):
        assert _raw_project_ids() == {str(project_a.id)}
    with tenant_context(project_b.organization_id):
        assert _raw_project_ids() == {str(project_b.id)}


def test_no_tenant_means_no_rows_even_unscoped(project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    assert _raw_project_ids() == set()
    assert Project.objects.count() == 0
    # The deliberately unscoped manager is still filtered by the database.
    assert Project.all_tenants.count() == 0


def test_database_refuses_insert_for_another_tenant(org_a, org_b) -> None:  # type: ignore[no-untyped-def]
    with (
        tenant_context(org_a.id),
        pytest.raises(ProgrammingError, match="row-level security"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO tenancy_project (id, organization_id, name, url, kind, created_at)"
            " VALUES (gen_random_uuid(), %s, 'sneaky', '', 'web_app', now())",
            [str(org_b.id)],
        )


def test_database_refuses_moving_a_row_to_another_tenant(project_a, org_b) -> None:  # type: ignore[no-untyped-def]
    with (
        tenant_context(project_a.organization_id),
        pytest.raises(ProgrammingError, match="row-level security"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE tenancy_project SET organization_id = %s WHERE id = %s",
            [str(org_b.id), str(project_a.id)],
        )


def test_save_refuses_without_tenant(org_a) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TenantContextError):
        Project(organization=org_a, name="x").save()


def test_save_refuses_for_another_tenant(org_a, org_b) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(org_a.id), pytest.raises(TenantContextError):
        Project(organization=org_b, name="x").save()


def test_tenant_context_restores_previous_tenant(org_a, org_b) -> None:  # type: ignore[no-untyped-def]
    ProjectFactory(organization=org_a)
    ProjectFactory(organization=org_b)
    with tenant_context(org_a.id):
        with tenant_context(org_b.id):
            assert Project.objects.get().organization_id == org_b.id
        assert Project.objects.get().organization_id == org_a.id
        assert len(_raw_project_ids()) == 1
    assert _raw_project_ids() == set()
