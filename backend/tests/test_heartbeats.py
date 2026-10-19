"""Heartbeat URLs and the alerts they drive."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
import time_machine
from django.core import mail
from django.db import connection
from django.test import Client

from commandr.ingest.models import Heartbeat, HeartbeatPing
from commandr.integrations.models import Connection, ConnectionStatus
from commandr.integrations.setup import get_setup
from commandr.monitoring import tasks
from commandr.monitoring.models import AlertState, Check, CheckStatus, Notification
from commandr.tenancy.context import tenant_context
from tests.factories import setup_connection

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_ingest")]

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


@pytest.fixture
def heartbeat(project_a, owner_a):  # type: ignore[no-untyped-def]
    with time_machine.travel(T0, tick=False):
        result = setup_connection(
            project_a, owner_a, "heartbeat", name="Nightly backup", period="3600", grace="900"
        )
    return urlsplit(result.reveal[0].value).path


def the_check(project) -> Check:  # type: ignore[no-untyped-def]
    with tenant_context(project.organization_id):
        return Check.objects.get(source="heartbeat")


def test_new_heartbeat_is_waiting_not_ok(heartbeat, project_a) -> None:  # type: ignore[no-untyped-def]
    check = the_check(project_a)
    assert check.status == CheckStatus.UNKNOWN
    assert "Waiting" in check.summary


def test_ping_records_and_connects(heartbeat, project_a) -> None:  # type: ignore[no-untyped-def]
    with time_machine.travel(T0 + timedelta(minutes=1), tick=False):
        assert Client().get(heartbeat).status_code == 204
    assert the_check(project_a).status == CheckStatus.OK
    with tenant_context(project_a.organization_id):
        assert Connection.objects.get().status == ConnectionStatus.CONNECTED
        assert HeartbeatPing.objects.count() == 1


def test_start_then_success_measures_duration(heartbeat, project_a) -> None:  # type: ignore[no-untyped-def]
    with time_machine.travel(T0, tick=False):
        assert Client().post(f"{heartbeat}/start").status_code == 204
    with time_machine.travel(T0 + timedelta(seconds=42), tick=False):
        assert Client().post(heartbeat).status_code == 204
    with tenant_context(project_a.organization_id):
        assert Heartbeat.objects.get().last_duration_ms == 42_000


def test_fail_with_message_alerts_and_redacts(
    heartbeat, project_a, owner_a, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    with django_capture_on_commit_callbacks(execute=True):
        response = Client().post(
            f"{heartbeat}/fail",
            data="Backup failed, token=supersecretvalue123",
            content_type="text/plain",
        )
    assert response.status_code == 204
    check = the_check(project_a)
    assert check.status == CheckStatus.FAIL
    assert check.alert_state == AlertState.ALERTING
    assert "supersecretvalue123" not in check.summary
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [owner_a.email]
    assert "Nightly backup is failing" in mail.outbox[0].subject


def test_missed_deadline_alerts_then_a_ping_recovers(
    heartbeat, project_a, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    with time_machine.travel(T0, tick=False):
        Client().get(heartbeat)
    # Due at +60 min, grace 15 min: still fine at +70.
    with time_machine.travel(T0 + timedelta(minutes=70), tick=False):
        tasks.evaluate()
    assert the_check(project_a).status == CheckStatus.OK
    with (
        time_machine.travel(T0 + timedelta(minutes=80), tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        tasks.evaluate()
    assert the_check(project_a).status == CheckStatus.FAIL
    assert [m.subject for m in mail.outbox] == ["[Commandr] Pantrini: Nightly backup is failing"]

    # Within the cooldown: no repeat. After it: one reminder.
    with (
        time_machine.travel(T0 + timedelta(minutes=100), tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        tasks.evaluate()
    assert len(mail.outbox) == 1
    with (
        time_machine.travel(T0 + timedelta(minutes=141), tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        tasks.evaluate()
    assert "still failing" in mail.outbox[-1].subject

    with (
        time_machine.travel(T0 + timedelta(minutes=150), tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        Client().get(heartbeat)
    assert "passing again" in mail.outbox[-1].subject
    assert the_check(project_a).alert_state == AlertState.OK


def test_unknown_and_revoked_tokens_are_404(heartbeat, project_a) -> None:  # type: ignore[no-untyped-def]
    assert Client().get("/v1/heartbeat/not-a-real-token-at-all-xx").status_code == 404
    with tenant_context(project_a.organization_id):
        conn = Connection.objects.select_related("project").get()
        get_setup("heartbeat").disconnect(conn)  # type: ignore[union-attr]
    assert Client().get(heartbeat).status_code == 404


def test_rate_limited_per_heartbeat(heartbeat, settings) -> None:  # type: ignore[no-untyped-def]
    settings.HEARTBEAT_RATE_LIMIT_PER_MINUTE = 1
    assert Client().get(heartbeat).status_code == 204
    response = Client().get(heartbeat)
    assert response.status_code == 429
    assert "Retry-After" in response


def test_heartbeat_rows_are_invisible_to_another_tenant(heartbeat, project_a, project_b) -> None:  # type: ignore[no-untyped-def]
    Client().get(heartbeat)
    for table in ("ingest_heartbeat", "ingest_heartbeatping", "monitoring_check"):
        with tenant_context(project_b.organization_id), connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            assert cursor.fetchone()[0] == 0, table
        with tenant_context(project_a.organization_id), connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            assert cursor.fetchone()[0] >= 1, table


def test_sending_a_notification_twice_sends_one_email(
    heartbeat, project_a, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    with django_capture_on_commit_callbacks(execute=True):
        Client().post(f"{heartbeat}/fail")
    with tenant_context(project_a.organization_id):
        notification = Notification.objects.get()
    tasks.send_notification(str(notification.id), str(project_a.organization_id))
    tasks.send_notification(str(notification.id), str(project_a.organization_id))
    assert len(mail.outbox) == 1
