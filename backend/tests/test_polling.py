"""Status-endpoint polling and uptime probes: signed, through safe_http, no DB in egress."""

import hashlib
import hmac
import json
import ssl
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import time_machine
from django.core import mail

from commandr.core.safe_http import SafeHttpClient
from commandr.integrations.models import Connection, ConnectionStatus
from commandr.monitoring import signing, tasks
from commandr.monitoring.models import (
    Check,
    CheckStatus,
    MetricPoint,
    MetricSeries,
    StatusEndpoint,
    UptimeMonitor,
)
from commandr.tenancy.context import tenant_context
from tests.factories import setup_connection

pytestmark = pytest.mark.django_db

URL = "https://api.pantrini.test/.well-known/commandr/status?probe=1"


def doc(**overrides):  # type: ignore[no-untyped-def]
    body = {
        "schema": "commandr.status/v1",
        "service": "pantrini-api",
        "checks": [
            {"key": "database", "name": "PostgreSQL", "status": "ok", "summary": "reachable"},
            {"key": "disk:External", "name": "External volume", "status": "warn", "value": 0.86},
        ],
        "gauges": [{"name": "queue.depth", "value": 3, "attrs": {"queue": "celery"}}],
        "kpis": [
            {"name": "user.total", "label": "Users", "value": 412, "unit": "count"},
            {"name": "revenue.mrr", "label": "MRR", "value": None},
        ],
    }
    body.update(overrides)
    return body


# --- Signing ---------------------------------------------------------------------


def test_signature_known_answer() -> None:
    # HMAC-SHA256("s3cret", "1760600000.GET./.well-known/commandr/status"), hex.
    header = signing.sign("s3cret", "get", "/.well-known/commandr/status", 1760600000)
    expected = hmac.new(
        b"s3cret", b"1760600000.GET./.well-known/commandr/status", hashlib.sha256
    ).hexdigest()
    assert header == f"t=1760600000,v1={expected}"
    assert signing.verify("s3cret", header, "GET", "/.well-known/commandr/status", 1760600100)
    assert not signing.verify("s3cret", header, "GET", "/.well-known/commandr/status", 1760600301)
    assert not signing.verify("other", header, "GET", "/.well-known/commandr/status", 1760600000)
    assert not signing.verify("s3cret", "garbage", "GET", "/", 1760600000)
    assert signing.signed_path(URL) == "/.well-known/commandr/status"


# --- Status endpoint ---------------------------------------------------------------


@pytest.fixture
def endpoint(project_a, owner_a, http, django_capture_on_commit_callbacks):  # type: ignore[no-untyped-def]
    """Set up through the real handler; its immediate signed test poll is captured."""
    secret_box: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not signing.verify(
            secret_box["secret"],
            request.headers["x-commandr-signature"],
            "GET",
            request.url.path,
            int(datetime.now(UTC).timestamp()),
        ):
            return httpx.Response(401)
        return httpx.Response(200, json=doc(), headers={"ETag": '"v1"'})

    http.handler = handler
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        result = setup_connection(project_a, owner_a, "status_endpoint", url=URL, interval="300")
    secret_box["secret"] = result.reveal[0].value
    for callback in callbacks:
        callback()
    return result


def _checks(project):  # type: ignore[no-untyped-def]
    with tenant_context(project.organization_id):
        return {c.key: c for c in Check.objects.all()}


def test_first_poll_is_signed_and_applied(endpoint, project_a, http) -> None:  # type: ignore[no-untyped-def]
    request = http.requests[0]
    assert request.headers["host"] == "api.pantrini.test"
    assert request.headers["x-commandr-project"] == f"prj_{project_a.id.hex}"
    assert request.headers["user-agent"].startswith("Commandr-Poller/1")
    assert endpoint.reveal[0].value.startswith("cmdr_sign_")

    checks = _checks(project_a)
    assert checks["commandr.reachability"].status == CheckStatus.OK
    assert checks["database"].status == CheckStatus.OK
    assert checks["disk:External"].status == CheckStatus.WARN
    with tenant_context(project_a.organization_id):
        kpis = {s.name: s for s in MetricSeries.objects.filter(kind="kpi")}
        assert kpis["user.total"].last_value == 412
        assert kpis["revenue.mrr"].last_value is None  # not available: never 0
        assert MetricPoint.objects.filter(series__name="revenue.mrr").count() == 0
        assert MetricPoint.objects.filter(series__name="queue.depth").count() == 1
        assert Connection.objects.get().status == ConnectionStatus.CONNECTED
        assert StatusEndpoint.objects.get().etag == '"v1"'


def _poll(project) -> None:  # type: ignore[no-untyped-def]
    with tenant_context(project.organization_id):
        tasks.enqueue_status_poll(StatusEndpoint.objects.get())


def test_absent_check_is_recovered_and_removed(
    endpoint, project_a, http, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    failing = doc(checks=[{"key": "route:/api/x", "name": "/api/x", "status": "fail"}])
    http.handler = lambda r: httpx.Response(200, json=failing)
    with django_capture_on_commit_callbacks(execute=True):
        _poll(project_a)
    assert _checks(project_a)["route:/api/x"].status == CheckStatus.FAIL
    assert "is failing" in mail.outbox[-1].subject

    http.handler = lambda r: httpx.Response(200, json=doc(checks=[]))
    with django_capture_on_commit_callbacks(execute=True):
        _poll(project_a)
    assert set(_checks(project_a)) == {"commandr.reachability"}
    assert "passing again" in mail.outbox[-1].subject


def test_etag_is_sent_and_304_counts_as_reachable(endpoint, project_a, http) -> None:  # type: ignore[no-untyped-def]
    http.handler = lambda r: httpx.Response(304)
    _poll(project_a)
    assert http.requests[-1].headers["if-none-match"] == '"v1"'
    checks = _checks(project_a)
    assert checks["commandr.reachability"].status == CheckStatus.OK
    assert checks["database"].status == CheckStatus.OK  # kept, not wiped


@pytest.mark.parametrize(
    ("handler", "expect"),
    [
        (lambda r: httpx.Response(401), "refused our signature"),
        (lambda r: httpx.Response(500), "got 500"),
        (lambda r: httpx.Response(200, text="<html>"), "not valid JSON"),
        (lambda r: httpx.Response(200, json={"schema": "nope"}), "does not match the contract"),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)), "timed out"),
        (lambda r: httpx.Response(302, headers={"location": "https://elsewhere.test/"}), "got 302"),
    ],
)
def test_bad_answers_fail_reachability(endpoint, project_a, http, handler, expect) -> None:  # type: ignore[no-untyped-def]
    http.handler = handler
    _poll(project_a)
    reach = _checks(project_a)["commandr.reachability"]
    assert reach.status == CheckStatus.FAIL
    assert expect in reach.summary


def test_wrong_secret_keeps_a_new_connection_waiting_with_the_reason(
    project_a, owner_a, http, django_capture_on_commit_callbacks
) -> None:  # type: ignore[no-untyped-def]
    http.handler = lambda r: httpx.Response(401)
    with django_capture_on_commit_callbacks(execute=True):
        setup_connection(project_a, owner_a, "status_endpoint", url=URL, interval="300")
    with tenant_context(project_a.organization_id):
        conn = Connection.objects.get()
    assert conn.status == ConnectionStatus.PENDING
    assert "signature" in conn.last_error


def test_dns_turning_private_is_refused_at_fetch(endpoint, project_a, http, public_dns) -> None:  # type: ignore[no-untyped-def]
    public_dns["api.pantrini.test"] = ["10.0.0.7"]
    before = len(http.requests)
    _poll(project_a)
    assert len(http.requests) == before  # never connected
    assert "not reachable from Commandr" in _checks(project_a)["commandr.reachability"].summary


def test_the_egress_task_does_not_touch_the_database(
    http, monkeypatch, django_assert_num_queries
) -> None:  # type: ignore[no-untyped-def]
    handed: list[dict] = []
    monkeypatch.setattr(tasks.record_status_result, "delay", lambda *args: handed.append(args[2]))
    http.handler = lambda r: httpx.Response(200, json=doc())
    with django_assert_num_queries(0):
        tasks.fetch_status("e", "o", URL, {"X-Commandr-Signature": "t=1,v1=x"})
    assert handed[0]["status_code"] == 200


def test_signing_secret_is_per_project_and_shown_once(project_a, owner_a, http) -> None:  # type: ignore[no-untyped-def]
    first = setup_connection(project_a, owner_a, "status_endpoint", url=URL, interval="300")
    second = setup_connection(
        project_a, owner_a, "status_endpoint", url="https://b.pantrini.test/s", interval="60"
    )
    assert len(first.reveal) == 1
    assert second.reveal == []


# --- Scheduling --------------------------------------------------------------------


def test_scheduler_claims_due_polls_once(project_a, owner_a, http, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    setup_connection(
        project_a, owner_a, "uptime_probe", url="https://pantrini.test/healthz/", interval="60"
    )
    calls: list[str] = []
    monkeypatch.setattr(tasks, "enqueue_uptime_probe", lambda m: calls.append(str(m.id)))
    assert tasks.schedule_polls() == 0  # first run is one interval out (we probed at setup)
    with time_machine.travel(datetime.now(UTC) + timedelta(seconds=61)):
        assert tasks.schedule_polls() == 1
        assert tasks.schedule_polls() == 0
    assert len(calls) == 1


# --- Uptime --------------------------------------------------------------------------


@pytest.fixture
def monitor(project_a, owner_a, http):  # type: ignore[no-untyped-def]
    setup_connection(
        project_a, owner_a, "uptime_probe", url="https://pantrini.test/healthz/", interval="300"
    )
    with tenant_context(project_a.organization_id):
        return UptimeMonitor.objects.get()


def _probe_result(project, monitor, **result):  # type: ignore[no-untyped-def]
    tasks.record_uptime_result(
        str(monitor.id),
        str(project.organization_id),
        {"status_code": 200, "response_ms": 120, "tls_not_after": None, "error": "", **result},
        datetime.now(UTC).isoformat(),
    )
    return _checks(project)


def test_uptime_up_down_and_metrics(project_a, monitor) -> None:  # type: ignore[no-untyped-def]
    checks = _probe_result(project_a, monitor)
    assert checks["uptime"].status == CheckStatus.OK
    assert checks["uptime"].summary == "HTTP 200 in 120 ms"
    checks = _probe_result(project_a, monitor, status_code=503)
    assert checks["uptime"].status == CheckStatus.FAIL
    checks = _probe_result(project_a, monitor, status_code=None, error="The request timed out.")
    assert checks["uptime"].summary == "The request timed out."
    with tenant_context(project_a.organization_id):
        assert set(MetricSeries.objects.values_list("name", flat=True)) >= {
            "uptime.up",
            "uptime.response_ms",
        }
        assert Connection.objects.get().status == ConnectionStatus.CONNECTED


@pytest.mark.parametrize(("days", "status"), [(60, "ok"), (10, "warn"), (2, "fail")])
def test_tls_expiry(project_a, monitor, days, status) -> None:  # type: ignore[no-untyped-def]
    expires = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    checks = _probe_result(project_a, monitor, tls_not_after=expires)
    assert checks["tls"].status == status
    with tenant_context(project_a.organization_id):
        assert MetricSeries.objects.get(name="uptime.tls_expires_at").last_value == pytest.approx(
            datetime.fromisoformat(expires).timestamp()
        )


def test_probe_task_uses_safe_http_and_follows_validated_redirects(
    project_a, monitor, http
) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz/":
            return httpx.Response(301, headers={"location": "/healthz/ok"})
        return httpx.Response(200)

    http.handler = handler
    tasks.probe_uptime(str(monitor.id), str(project_a.organization_id), monitor.url)
    assert _checks(project_a)["uptime"].status == CheckStatus.OK
    assert [r.url.path for r in http.requests[-2:]] == ["/healthz/", "/healthz/ok"]


def test_peer_certificate_expiry_is_read(monkeypatch, public_dns) -> None:  # type: ignore[no-untyped-def]
    class FakeSSL(ssl.SSLObject):
        def __init__(self) -> None:  # bypass the real constructor
            pass

        def getpeercert(self, binary_form=False):  # type: ignore[no-untyped-def]
            return {"notAfter": "Jun  1 12:00:00 2027 GMT"}

    class Stream:
        def get_extra_info(self, name):  # type: ignore[no-untyped-def]
            return FakeSSL() if name == "ssl_object" else None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, extensions={"network_stream": Stream()})

    response = SafeHttpClient(transport=httpx.MockTransport(handler)).get("https://pantrini.test/")
    assert response.tls_not_after == datetime(2027, 6, 1, 12, 0, tzinfo=UTC)


def test_setup_refuses_private_addresses(project_a, owner_a, public_dns) -> None:  # type: ignore[no-untyped-def]
    from rest_framework.exceptions import ValidationError

    public_dns["intranet.test"] = ["192.168.1.10"]
    with pytest.raises(ValidationError, match="not reachable"):
        setup_connection(
            project_a, owner_a, "uptime_probe", url="https://intranet.test/", interval="60"
        )
    with pytest.raises(ValidationError, match="https"):
        setup_connection(project_a, owner_a, "status_endpoint", url="http://x.test/", interval="60")


def test_poll_payload_is_json_serialisable_and_has_no_secret(
    endpoint, project_a, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    sent: list[dict] = []
    monkeypatch.setattr(tasks.fetch_status, "apply_async", lambda **kw: sent.append(kw))
    _poll(project_a)
    payload = json.dumps(sent[0]["args"])
    assert endpoint.reveal[0].value not in payload
    assert sent[0]["expires"] == tasks.EGRESS_EXPIRES
