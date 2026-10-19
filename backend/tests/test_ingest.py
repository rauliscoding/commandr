"""POST /v1/ingest: the push API (ingestion-contract.md § Push API)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import redis
import yaml
from django.db import connection
from django.test import Client

from commandr.ingest import stream
from commandr.ingest.models import IngestKey
from commandr.ingest.schemas import SCHEMAS
from commandr.integrations.models import Connection, ConnectionStatus
from commandr.monitoring.models import (
    ErrorGroup,
    ErrorOccurrence,
    Event,
    MetricPoint,
    MetricRollup1m,
    MetricSeries,
)
from commandr.tenancy.context import tenant_context
from tests.factories import setup_connection

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_ingest")]

OPENAPI = Path(__file__).resolve().parents[2] / "docs/architecture/openapi/ingest-v1.yaml"


def now_iso(delta: timedelta = timedelta()) -> str:
    return (datetime.now(UTC) + delta).isoformat()


def batch(**sections):  # type: ignore[no-untyped-def]
    return {"schema": "commandr.ingest/v1", **sections}


def gauge(name="queue.depth", value=3, **extra):  # type: ignore[no-untyped-def]
    return {"name": name, "type": "gauge", "value": value, "ts": now_iso(), **extra}


@pytest.fixture
def push_key(project_a, owner_a):  # type: ignore[no-untyped-def]
    result = setup_connection(project_a, owner_a, "push_api", name="Production", environment="live")
    return result.reveal[0].value


@pytest.fixture
def push_key_b(project_b, owner_b):  # type: ignore[no-untyped-def]
    result = setup_connection(project_b, owner_b, "push_api", name="Other", environment="test")
    return result.reveal[0].value


def post(body, key=None, **headers):  # type: ignore[no-untyped-def]
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    if key:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {key}"
    data = body if isinstance(body, (str, bytes)) else json.dumps(body)
    return Client().post("/v1/ingest", data=data, content_type="application/json", **extra)


def drain(client) -> int:  # type: ignore[no-untyped-def]
    return stream.drain_once(client, "test")


# --- Contract ------------------------------------------------------------------


def test_server_schemas_match_the_published_openapi_file() -> None:
    published = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]
    assert published == SCHEMAS


def test_key_format_and_storage(push_key, project_a) -> None:  # type: ignore[no-untyped-def]
    assert push_key.startswith("cmdr_ingest_live_")
    assert len(push_key) == len("cmdr_ingest_live_") + 43
    with tenant_context(project_a.organization_id):
        key = IngestKey.objects.get()
        assert key.last4 == push_key[-4:]
        assert push_key not in {key.key_hash, key.name}
        with connection.cursor() as cursor:
            cursor.execute("SELECT row_to_json(k)::text FROM ingest_ingestkey k")
            assert push_key not in cursor.fetchone()[0]


# --- Happy path and write path ---------------------------------------------------


def test_accepts_writes_and_marks_the_connection_connected(
    push_key, project_a, fake_stream
) -> None:  # type: ignore[no-untyped-def]
    body = batch(
        resource={"service": "pantrini-api"},
        metrics=[
            gauge(),
            {
                "name": "http.server.requests",
                "type": "counter",
                "value": 12,
                "ts": now_iso(),
                "interval_s": 60,
                "attrs": {"route": "api/pantries/", "status_class": "2xx"},
            },
        ],
        events=[
            {"id": "evt_1", "name": "user.signup", "ts": now_iso(), "props": {"plan": "trial"}}
        ],
        errors=[
            {
                "id": "err_1",
                "ts": now_iso(),
                "level": "error",
                "fingerprint": "sha1:abc",
                "type": "KeyError",
                "message": "'unit'",
                "stack": "Traceback… Authorization: Bearer abcdefghijklmnop0123",
            }
        ],
    )
    response = post(body, push_key)
    assert response.status_code == 202, response.content
    assert response.json() == {"accepted": 4, "rejected": []}
    assert drain(fake_stream) == 1

    with tenant_context(project_a.organization_id):
        assert MetricSeries.objects.count() == 2
        assert MetricPoint.objects.count() == 2
        assert MetricRollup1m.objects.count() == 2
        assert Event.objects.get().name == "user.signup"
        group = ErrorGroup.objects.get()
        assert group.count == 1
        assert "abcdefghijklmnop0123" not in ErrorOccurrence.objects.get().stack
        conn = Connection.objects.get()
        assert conn.status == ConnectionStatus.CONNECTED
        assert conn.first_data_at is not None
        key = IngestKey.objects.get()
        assert key.last_used_at is not None
        assert key.last_used_ip == "127.0.0.1"


def test_replaying_a_stream_entry_writes_nothing_twice(push_key, project_a, fake_stream) -> None:  # type: ignore[no-untyped-def]
    post(batch(metrics=[gauge()], events=[{"id": "e1", "name": "x.y", "ts": now_iso()}]), push_key)
    (_, entries), *_ = fake_stream.xread({"cmdr:ingest": "0"})
    fields = {k.decode(): v.decode() for k, v in entries[0][1].items()}
    stream.process(fields)
    stream.process(fields)
    with tenant_context(project_a.organization_id):
        assert MetricPoint.objects.count() == 1
        rollup = MetricRollup1m.objects.get()
        assert rollup.count == 1
        assert Event.objects.count() == 1


def test_points_are_invisible_to_another_tenant(
    push_key, project_a, project_b, fake_stream
) -> None:  # type: ignore[no-untyped-def]
    post(batch(metrics=[gauge()]), push_key)
    drain(fake_stream)
    with tenant_context(project_b.organization_id), connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM monitoring_metricpoint")
        assert cursor.fetchone()[0] == 0
    with tenant_context(project_a.organization_id), connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM monitoring_metricpoint")
        assert cursor.fetchone()[0] == 1


# --- Partial acceptance ----------------------------------------------------------


def test_bad_items_are_rejected_one_by_one(push_key, fake_stream) -> None:  # type: ignore[no-untyped-def]
    body = batch(
        metrics=[
            gauge(),  # 0 ok
            gauge(name="Bad Name"),  # 1 invalid
            gauge(ts=now_iso(-timedelta(hours=25))),  # 2 too_old
            gauge(ts=now_iso(timedelta(minutes=10))),  # 3 in_future
            gauge(attrs={"email": "x"}),  # 4 personal key
            gauge(attrs={"who": "ana@example.com"}),  # 5 personal value
            gauge(ts="2026-10-16T06:00:00"),  # 6 no time zone
        ],
        events=[
            {"id": "a", "name": "user.signup", "ts": now_iso()},
            {"id": "a", "name": "user.signup", "ts": now_iso()},  # duplicate in batch
            {"name": "user.signup", "ts": now_iso(), "props": {"ip": "1.2.3.4"}},
        ],
    )
    response = post(body, push_key)
    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] == 2
    codes = {(r["section"], r["index"]): r["code"] for r in data["rejected"]}
    assert codes == {
        ("metrics", 1): "invalid",
        ("metrics", 2): "too_old",
        ("metrics", 3): "in_future",
        ("metrics", 4): "personal_data",
        ("metrics", 5): "personal_data",
        ("metrics", 6): "invalid",
        ("events", 1): "duplicate",
        ("events", 2): "personal_data",
    }


def test_cardinality_cap_rejects_with_a_reason(push_key, settings, fake_stream) -> None:  # type: ignore[no-untyped-def]
    settings.INGEST_MAX_ATTR_VALUES = 2
    metrics = [gauge(attrs={"route": f"r{i}"}) for i in range(3)]
    data = post(batch(metrics=metrics), push_key).json()
    assert data["accepted"] == 2
    assert data["rejected"][0]["code"] == "cardinality_limit"
    assert "'route'" in data["rejected"][0]["message"]
    drain(fake_stream)
    # Known series stay accepted; a new value is still refused.
    data = post(
        batch(metrics=[gauge(attrs={"route": "r0"}), gauge(attrs={"route": "r9"})]), push_key
    ).json()
    assert data["accepted"] == 1
    assert data["rejected"][0]["index"] == 1


def test_series_cap_per_project(push_key, settings, fake_stream) -> None:  # type: ignore[no-untyped-def]
    settings.INGEST_MAX_SERIES_PER_PROJECT = 1
    data = post(batch(metrics=[gauge(name="a.b"), gauge(name="c.d")]), push_key).json()
    assert data["accepted"] == 1
    assert data["rejected"][0]["code"] == "cardinality_limit"


# --- Whole-request failures --------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        json.dumps({"schema": "commandr.ingest/v2"}),
        json.dumps({"schema": "commandr.ingest/v1", "metricz": []}),  # typo: unknown field
        json.dumps({"schema": "commandr.ingest/v1", "metrics": {}}),
    ],
)
def test_malformed_requests_are_400(push_key, body) -> None:  # type: ignore[no-untyped-def]
    response = post(body, push_key)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"


@pytest.mark.parametrize("key", [None, "cmdr_ingest_live_nope", "Basic abc"])
def test_bad_or_missing_key_is_401(key) -> None:  # type: ignore[no-untyped-def]
    response = post(batch(), key)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_key"


def test_too_large_is_413(push_key) -> None:  # type: ignore[no-untyped-def]
    huge = json.dumps(
        batch(events=[{"name": "a.b", "ts": now_iso(), "props": {"x": "y" * 200}}] * 6000)
    )
    assert post(huge, push_key).status_code == 413
    many = batch(metrics=[gauge()] * 600, events=[{"name": "a.b", "ts": now_iso()}] * 401)
    response = post(many, push_key)
    assert response.status_code == 413
    assert response.json()["code"] == "too_many_items"


def test_rate_limit_is_per_key(push_key, push_key_b, settings, fake_stream) -> None:  # type: ignore[no-untyped-def]
    settings.INGEST_RATE_LIMIT_PER_MINUTE = 2
    assert post(batch(), push_key).status_code == 202
    assert post(batch(), push_key).status_code == 202
    limited = post(batch(), push_key)
    assert limited.status_code == 429
    assert int(limited["Retry-After"]) >= 1
    # Another customer's key is not throttled by the first one's traffic.
    assert post(batch(), push_key_b).status_code == 202


def test_redis_down_is_503_with_retry_after(push_key, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class Down:
        def xadd(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise redis.ConnectionError("down")

    monkeypatch.setattr(stream, "get_client", lambda: Down())
    response = post(batch(metrics=[gauge()]), push_key)
    assert response.status_code == 503
    assert response["Retry-After"] == "30"


def test_idempotency_key_replays_the_first_answer(push_key, fake_stream) -> None:  # type: ignore[no-untyped-def]
    body = batch(metrics=[gauge(), gauge(name="Bad")])
    first = post(body, push_key, **{"Idempotency-Key": "01JA9Z"})
    second = post(body, push_key, **{"Idempotency-Key": "01JA9Z"})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert fake_stream.xlen("cmdr:ingest") == 1
    post(body, push_key, **{"Idempotency-Key": "another"})
    assert fake_stream.xlen("cmdr:ingest") == 2


def test_revoked_key_is_refused_at_once(push_key, project_a, fake_stream) -> None:  # type: ignore[no-untyped-def]
    from commandr.integrations.setup import get_setup

    assert post(batch(), push_key).status_code == 202
    with tenant_context(project_a.organization_id):
        conn = Connection.objects.select_related("project").get()
        get_setup("push_api").disconnect(conn)  # type: ignore[union-attr]
        assert IngestKey.objects.get().revoked_at is not None
    assert post(batch(), push_key).status_code == 401


def test_forwarded_for_is_believed_only_from_a_trusted_proxy(
    push_key, project_a, settings, fake_stream
) -> None:  # type: ignore[no-untyped-def]
    post(batch(), push_key, **{"X-Forwarded-For": "203.0.113.9"})
    with tenant_context(project_a.organization_id):
        assert IngestKey.objects.get().last_used_ip == "127.0.0.1"

    from django.core.cache import cache

    cache.clear()
    settings.TRUSTED_PROXY_CIDRS = ["127.0.0.0/8"]
    post(batch(), push_key, **{"X-Forwarded-For": "198.51.100.1, 203.0.113.9"})
    with tenant_context(project_a.organization_id):
        assert IngestKey.objects.get().last_used_ip == "203.0.113.9"


def test_get_is_not_allowed() -> None:
    assert Client().get("/v1/ingest").status_code == 405
