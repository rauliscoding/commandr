"""Row-level security on every Phase 1 table, including each metric partition.

Each test goes around the application (raw SQL) with org B active and asserts
org A's rows are invisible: the database alone must stop the leak.
"""

from datetime import UTC, datetime

import pytest
from django.db import ProgrammingError, connection, transaction

from commandr.monitoring.models import AlertRule
from commandr.monitoring.write import MetricIn, write_errors, write_events, write_metrics
from commandr.tenancy.context import tenant_context
from tests.factories import setup_connection

pytestmark = pytest.mark.django_db

TABLES = [
    "ingest_ingestkey",
    "ingest_heartbeat",
    "ingest_signingsecret",
    "monitoring_metricseries",
    "monitoring_metricpoint",
    "monitoring_metricrollup1m",
    "monitoring_metricrollup1h",
    "monitoring_event",
    "monitoring_errorgroup",
    "monitoring_erroroccurrence",
    "monitoring_check",
    "monitoring_alertrule",
    "monitoring_uptimemonitor",
    "monitoring_statusendpoint",
]


def _count(table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — constant table names
        return int(cursor.fetchone()[0])


def _partition_now() -> str:
    return f"monitoring_metricpoint_p{datetime.now(UTC):%Y%m}"


@pytest.fixture
def org_a_data(project_a, owner_a, public_dns, django_capture_on_commit_callbacks):  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    with django_capture_on_commit_callbacks(execute=False):  # no polls: no network here
        setup_connection(project_a, owner_a, "push_api", name="Prod")
        setup_connection(project_a, owner_a, "heartbeat", name="Backup")
        setup_connection(project_a, owner_a, "uptime_probe", url="https://a.test/")
        setup_connection(project_a, owner_a, "status_endpoint", url="https://a.test/s")
    with tenant_context(project_a.organization_id):
        write_metrics(project_a.id, [MetricIn("queue.depth", "gauge", 3, now)])
        write_events(project_a.id, [{"name": "user.signup", "ts": now}])
        write_errors(
            project_a.id,
            [{"ts": now, "level": "error", "fingerprint": "f", "message": "boom"}],
        )
        AlertRule.objects.create(project=project_a, name="r", metric="queue.depth", kind="absence")


def test_every_table_hides_another_tenants_rows(org_a_data, project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(project_a.organization_id):
        for table in TABLES:
            assert _count(table) >= 1, f"{table}: expected org A's rows"
    with tenant_context(project_b.organization_id):
        for table in TABLES:
            assert _count(table) == 0, f"{table}: org B can see org A's rows"
    for table in TABLES:  # and with no tenant at all
        assert _count(table) == 0, table


def test_a_partition_queried_directly_is_filtered_too(org_a_data, project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    partition = _partition_now()
    with tenant_context(project_a.organization_id):
        assert _count(partition) == 1
    with tenant_context(project_b.organization_id):
        assert _count(partition) == 0


def test_every_partition_has_rls_forced() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT monitoring_ensure_point_partitions(1, 3)")
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
            WHERE i.inhparent = 'monitoring_metricpoint'::regclass
            """
        )
        rows = cursor.fetchall()
    assert len(rows) >= 5  # last month, this month, three ahead
    assert all(enabled and forced for _, enabled, forced in rows), rows


def test_points_cannot_be_written_for_another_tenant(org_a, org_b, project_a) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(org_a.id):
        write_metrics(project_a.id, [MetricIn("x.y", "gauge", 1, datetime.now(UTC))])
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM monitoring_metricseries")
            series_id = cursor.fetchone()[0]
        with (
            pytest.raises(ProgrammingError, match="row-level security"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "INSERT INTO monitoring_metricpoint (organization_id, series_id, ts, value)"
                " VALUES (%s, %s, now(), 1)",
                [str(org_b.id), series_id],
            )


def test_old_partitions_are_dropped_whole() -> None:
    from datetime import timedelta

    with connection.cursor() as cursor:
        cursor.execute("SELECT monitoring_ensure_point_partitions(2, 0)")
        cursor.execute(
            "SELECT monitoring_drop_point_partitions(%s)",
            [datetime.now(UTC).replace(day=1) - timedelta(days=1)],
        )
        cursor.execute(
            "SELECT count(*) FROM pg_class WHERE relname = %s",
            [f"monitoring_metricpoint_p{datetime.now(UTC):%Y%m}"],
        )
        assert cursor.fetchone()[0] == 1  # this month survives
