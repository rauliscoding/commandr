"""The notification state machine and the daily digest."""

from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from django.core import mail

from commandr.monitoring import checks, digest, tasks
from commandr.monitoring.alerts import Action, on_disappear, transition
from commandr.monitoring.health import Verdict
from commandr.monitoring.models import AlertState, CheckSource, CheckStatus, Notification
from commandr.tenancy.context import tenant_context
from commandr.tenancy.models import Role
from tests.factories import MembershipFactory

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
COOLDOWN = timedelta(hours=1)


@pytest.mark.parametrize(
    ("state", "last", "status", "expected"),
    [
        (AlertState.OK, None, CheckStatus.FAIL, (AlertState.ALERTING, Action.ALERT)),
        (
            AlertState.ALERTING,
            NOW - timedelta(minutes=10),
            CheckStatus.FAIL,
            (AlertState.ALERTING, None),
        ),
        (
            AlertState.ALERTING,
            NOW - timedelta(hours=1),
            CheckStatus.FAIL,
            (AlertState.ALERTING, Action.REMINDER),
        ),
        (AlertState.ALERTING, NOW, CheckStatus.OK, (AlertState.OK, Action.RECOVERY)),
        (AlertState.OK, None, CheckStatus.OK, (AlertState.OK, None)),
        (AlertState.OK, None, CheckStatus.WARN, (AlertState.OK, None)),
        # Unknown never counts as recovered, and never alerts by itself.
        (AlertState.ALERTING, NOW, CheckStatus.UNKNOWN, (AlertState.ALERTING, None)),
        (AlertState.OK, None, CheckStatus.UNKNOWN, (AlertState.OK, None)),
    ],
)
def test_transition_table(state, last, status, expected) -> None:  # type: ignore[no-untyped-def]
    assert (
        transition(
            alert_state=state, last_notified_at=last, status=status, now=NOW, cooldown=COOLDOWN
        )
        == expected
    )


def test_a_check_that_disappears_while_alerting_recovers() -> None:
    assert on_disappear(AlertState.ALERTING) is Action.RECOVERY
    assert on_disappear(AlertState.OK) is None


def _record(project, status, key="database", at=NOW):  # type: ignore[no-untyped-def]
    # The clock is moved too, so rows' created_at agree with `at`.
    with time_machine.travel(at, tick=False), tenant_context(project.organization_id):
        return checks.record(
            project=project,
            source=CheckSource.STATUS_ENDPOINT,
            source_id=project.id,
            result=checks.Result(key, key.title(), status),
            now=at,
            expected_every_seconds=300,
        )


@pytest.mark.django_db
def test_only_owners_and_admins_of_that_organization_are_emailed(
    project_a, owner_a, org_a, owner_b, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    admin = MembershipFactory(organization=org_a, role=Role.ADMIN).user
    MembershipFactory(organization=org_a, role=Role.MEMBER)
    with django_capture_on_commit_callbacks(execute=True):
        _record(project_a, CheckStatus.FAIL)
    assert sorted(m.to[0] for m in mail.outbox) == sorted([owner_a.email, admin.email])


@pytest.mark.django_db
def test_stale_checks_turn_unknown(project_a) -> None:  # type: ignore[no-untyped-def]
    _record(project_a, CheckStatus.OK)
    with tenant_context(project_a.organization_id):
        assert checks.mark_stale(project_a.id, NOW + timedelta(minutes=14)) == 0
        assert checks.mark_stale(project_a.id, NOW + timedelta(minutes=16)) == 1


# --- Digest ------------------------------------------------------------------------


@pytest.mark.django_db
def test_digest_says_nothing_was_checked_when_nothing_ran(project_a) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(project_a.organization_id):
        assert digest.build(project_a, NOW)["verdict"]["state"] == Verdict.NOTHING_CHECKED
    _record(project_a, CheckStatus.OK, at=NOW - timedelta(hours=30))
    with tenant_context(project_a.organization_id):
        assert digest.build(project_a, NOW)["verdict"]["state"] == Verdict.NOTHING_CHECKED


@pytest.mark.django_db
def test_digest_healthy_and_attention(project_a) -> None:  # type: ignore[no-untyped-def]
    _record(project_a, CheckStatus.OK)
    with tenant_context(project_a.organization_id):
        assert digest.build(project_a, NOW)["verdict"]["state"] == Verdict.HEALTHY
    _record(project_a, CheckStatus.WARN, key="disk")
    with tenant_context(project_a.organization_id):
        data = digest.build(project_a, NOW)
        assert data["verdict"]["state"] == Verdict.ATTENTION
        assert [c["name"] for c in data["attention"]] == ["Disk"]


@pytest.mark.django_db
def test_an_alert_in_the_last_day_means_attention_even_if_recovered(project_a) -> None:  # type: ignore[no-untyped-def]
    _record(project_a, CheckStatus.FAIL, at=NOW - timedelta(hours=2))
    _record(project_a, CheckStatus.OK, at=NOW - timedelta(hours=1))
    with tenant_context(project_a.organization_id):
        data = digest.build(project_a, NOW)
    assert data["verdict"]["state"] == Verdict.ATTENTION
    assert data["alerts_24h"] == 1


@pytest.mark.django_db
def test_digest_goes_out_once_a_day_from_the_digest_hour(
    project_a, owner_a, org_a, settings, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    settings.MONITORING_DIGEST_HOUR = 7
    org_a.timezone = "Europe/Lisbon"  # UTC+1 in October (WEST)
    org_a.save()
    with time_machine.travel(datetime(2026, 10, 18, 5, 30, tzinfo=UTC), tick=False):
        assert tasks.send_due_digests() == 0  # 06:30 in Lisbon
    with (
        time_machine.travel(datetime(2026, 10, 18, 6, 5, tzinfo=UTC), tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        assert tasks.send_due_digests() == 1  # 07:05 in Lisbon
        assert tasks.send_due_digests() == 0  # idempotent
    assert len(mail.outbox) == 1
    assert "Nothing was checked" in mail.outbox[0].subject
    assert "Nothing reported in the last 24 hours" in mail.outbox[0].body
    with tenant_context(org_a.id):
        assert Notification.objects.filter(kind="digest").count() == 1
