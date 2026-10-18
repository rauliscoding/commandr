import logging
import uuid

import pytest
from django.test import Client

from commandr.audit.models import AuditEvent
from commandr.audit.services import record
from commandr.core.ids import uuid7
from commandr.core.logging import RedactSecretsFilter, redact


def test_uuid7_has_version_7_and_sorts_by_time() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(isinstance(i, uuid.UUID) and i.version == 7 for i in ids)
    assert [i.int >> 80 for i in ids] == sorted(i.int >> 80 for i in ids)


@pytest.mark.parametrize(
    "secret",
    [
        "Authorization: Bearer abcdefghijklmnop123",
        # Fake keys, split so secret scanners do not flag the repository.
        "sk_" + "live_51Habcdefghijklmnop",
        "re_" + "123456789abcdefghijk",
        "cmdr_ingest_live_abcdefghijklmnopqrstuv",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        'password="hunter2hunter2"',
    ],
)
def test_redaction_masks_secret_shapes(secret: str) -> None:
    assert "[REDACTED]" in redact(f"calling provider with {secret} now")


def test_redaction_filter_rewrites_log_records() -> None:
    record_ = logging.LogRecord("x", logging.INFO, __file__, 1, "token=%s", ("abc123secret",), None)
    RedactSecretsFilter().filter(record_)
    assert "abc123secret" not in record_.getMessage()


@pytest.mark.django_db
def test_healthz_is_shallow_and_public() -> None:
    response = Client().get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-Id"]


@pytest.mark.django_db
def test_csrf_endpoint_sets_the_cookie_the_spa_reads() -> None:
    response = Client().get("/api/csrf/")
    assert response.status_code == 204
    assert "csrftoken" in response.cookies
    assert not response.cookies["csrftoken"]["httponly"]  # the SPA must be able to read it


@pytest.mark.django_db
def test_audit_events_are_append_only(user) -> None:  # type: ignore[no-untyped-def]
    event = record("user.signed_in", actor=user)
    event.action = "rewritten"
    with pytest.raises(RuntimeError):
        event.save()
    assert AuditEvent.objects.get().action == "user.signed_in"


@pytest.mark.django_db
def test_audit_metadata_refuses_secrets(user) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="token"):
        record("connection.created", actor=user, metadata={"token": "x"})
