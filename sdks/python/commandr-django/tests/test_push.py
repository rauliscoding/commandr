"""Traffic, errors, events and heartbeats: what is pushed, and that it never hurts the host."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import pytest
from django.test import AsyncClient, Client

import commandr_django as commandr
from commandr_django import transport as transport_module
from commandr_django.handler import CommandrHandler
from commandr_django.traffic import route_template, traffic
from commandr_django.transport import transport

from .conftest import FakeIngest, assert_valid


def sent(ingest: FakeIngest, section: str) -> list[dict[str, Any]]:
    return [item for batch in ingest.batches() for item in batch.get(section, [])]


def by_name(items: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [i for i in items if i["name"] == name]


# --- The batch envelope ---------------------------------------------------------


def test_batch_matches_the_contract_and_carries_the_key(
    pushing: dict[str, Any], ingest: FakeIngest
) -> None:
    commandr.event("user.signup", plan="trial")
    transport.flush()
    [request] = ingest.received
    assert request.path == "/v1/ingest"
    assert request.headers["Authorization"] == f"Bearer {pushing['INGEST_KEY']}"
    assert request.headers["Content-Type"] == "application/json"
    assert len(request.headers["Idempotency-Key"]) == 32
    batch = request.json()
    assert_valid("IngestBatch", batch)
    assert batch["schema"] == "commandr.ingest/v1"
    assert batch["resource"] == {
        "service": "testproject",
        "version": "1.2.0",
        "environment": "test",
    }


def test_nothing_is_sent_without_an_ingest_key(settings: Any, ingest: FakeIngest) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url, "INGEST_KEY": ""}
    commandr.event("user.signup")
    transport.flush()
    assert ingest.received == []
    assert transport.pending()["events"] == 0


def test_disabled_sends_nothing(settings: Any, ingest: FakeIngest) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url, "ENABLED": False}
    commandr.event("user.signup")
    transport.flush()
    assert ingest.received == []


# --- Traffic --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("route", "template"),
    [
        ("api/items/<int:pk>/", "api/items/{pk}/"),
        ("api/<slug>/", "api/{slug}/"),
        ("^legacy/(?P<slug>[a-z]+)/$", "legacy/{slug}/"),
        ("", "/"),
    ],
)
def test_route_templates(route: str, template: str) -> None:
    assert route_template(route) == template


def test_traffic_is_aggregated_per_route_template(
    pushing: dict[str, Any], ingest: FakeIngest, client: Client
) -> None:
    for pk in (1, 2, 3):
        client.get(f"/api/items/{pk}/")
    client.get("/legacy/abc/")
    client.get("/no/such/page/")
    client.get("/.well-known/commandr/status")  # Commandr's own polls are not traffic
    transport.flush()

    metrics = sent(ingest, "metrics")
    for batch in ingest.batches():
        assert_valid("IngestBatch", batch)
    requests = {
        (m["attrs"]["route"], m["attrs"]["status_class"]): m
        for m in by_name(metrics, "http.server.requests")
    }
    assert set(requests) == {
        ("api/items/{pk}/", "2xx"),
        ("legacy/{slug}/", "2xx"),
        ("unmatched", "4xx"),
    }
    items = requests[("api/items/{pk}/", "2xx")]
    assert items["type"] == "counter"
    assert items["value"] == 3
    assert items["interval_s"] >= 1
    durations = by_name(metrics, "http.server.duration_ms")
    assert {(d["attrs"]["route"], d["attrs"]["quantile"]) for d in durations} >= {
        ("api/items/{pk}/", "p50"),
        ("api/items/{pk}/", "p95"),
    }
    assert all(d["type"] == "gauge" and d["unit"] == "ms" for d in durations)


def test_traffic_window_is_reset_after_a_flush(
    pushing: dict[str, Any], ingest: FakeIngest, client: Client
) -> None:
    client.get("/api/items/1/")
    transport.flush()
    transport.flush()
    assert len(ingest.batches()) == 1


def test_each_process_stamps_its_own_sub_second_offset(
    pushing: dict[str, Any], ingest: FakeIngest, client: Client
) -> None:
    # The server de-duplicates by (series, ts): workers must not share timestamps.
    client.get("/api/items/1/")
    transport.flush()
    [metric] = by_name(sent(ingest, "metrics"), "http.server.requests")
    microseconds = int(metric["ts"].rsplit(".", 1)[1].rstrip("Z"))
    assert microseconds == transport.ts_offset_us != 0


def test_500_is_counted_and_the_error_captured(
    pushing: dict[str, Any], ingest: FakeIngest, client: Client
) -> None:
    client.raise_request_exception = False
    response = client.get("/boom/")
    assert response.status_code == 500
    transport.flush()
    requests = by_name(sent(ingest, "metrics"), "http.server.requests")
    assert [(m["attrs"]["route"], m["attrs"]["status_class"]) for m in requests] == [
        ("boom/", "5xx")
    ]
    [error] = sent(ingest, "errors")
    assert error["type"] == "KeyError"
    assert error["message"] == "'unit'"
    assert error["culprit"] == "tests.testproject.urls.boom" or error["culprit"].endswith(
        "urls.boom"
    )
    assert error["attrs"] == {"logger": "django.request", "route": "boom/"}
    assert error["fingerprint"].startswith("sha1:")


def test_async_views_are_counted(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    async def run() -> int:
        response = await AsyncClient().get("/async/")
        return int(response.status_code)

    assert asyncio.run(run()) == 200
    transport.flush()
    requests = by_name(sent(ingest, "metrics"), "http.server.requests")
    assert [m["attrs"]["route"] for m in requests] == ["async/"]


def test_too_many_routes_fold_into_other() -> None:
    from commandr_django import traffic as traffic_module

    for i in range(traffic_module.MAX_ROUTES + 10):
        traffic.record(f"r{i}/", 200, 1.0)
    routes = {m["attrs"]["route"] for m in traffic.collect() if m["name"] == "http.server.requests"}
    assert len(routes) == traffic_module.MAX_ROUTES + 1
    assert "other" in routes


def test_traffic_failure_never_reaches_the_request(
    pushing: dict[str, Any], client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any) -> None:
        raise RuntimeError("bug in the SDK")

    monkeypatch.setattr(traffic, "record", explode)
    assert client.get("/api/items/1/").status_code == 200


# --- Errors ---------------------------------------------------------------------


def _raise_key_error(key: str) -> None:
    empty: dict[str, int] = {}
    empty[key]


def test_logged_exception_is_sent_with_a_stable_fingerprint(
    pushing: dict[str, Any], ingest: FakeIngest
) -> None:
    log = logging.getLogger("myapp.orders")
    for key in ("a", "b"):
        try:
            _raise_key_error(key)
        except KeyError:
            log.exception("Order failed")
    transport.flush()
    errors = sent(ingest, "errors")
    assert len(errors) == 2
    for batch in ingest.batches():
        assert_valid("IngestBatch", batch)
    assert errors[0]["fingerprint"] == errors[1]["fingerprint"]  # same problem, one group
    assert errors[0]["id"] != errors[1]["id"]
    assert errors[0]["level"] == "error"
    assert errors[0]["culprit"].endswith("test_push._raise_key_error")
    assert "Traceback" in errors[0]["stack"]


def test_log_without_exception_groups_by_template(
    pushing: dict[str, Any], ingest: FakeIngest
) -> None:
    log = logging.getLogger("myapp.payments")
    log.error("Payment %s failed", 1)
    log.error("Payment %s failed", 2)
    log.critical("Something else")
    log.warning("Not captured: below ERROR")
    transport.flush()
    errors = sent(ingest, "errors")
    assert [e["message"] for e in errors] == [
        "Payment 1 failed",
        "Payment 2 failed",
        "Something else",
    ]
    assert errors[0]["fingerprint"] == errors[1]["fingerprint"] != errors[2]["fingerprint"]
    assert errors[2]["level"] == "critical"


def test_one_group_is_capped_per_minute(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    log = logging.getLogger("myapp.loop")
    for _ in range(50):
        log.error("Same thing again")
    transport.flush()
    assert len(sent(ingest, "errors")) == 10


def test_the_sdks_own_warnings_are_not_captured(
    pushing: dict[str, Any], ingest: FakeIngest
) -> None:
    logging.getLogger("commandr_django").error("about ourselves")
    transport.flush()
    assert sent(ingest, "errors") == []


def test_handler_is_installed_once_on_the_root_logger() -> None:
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, CommandrHandler)]
    assert len(handlers) == 1


def test_long_stack_is_truncated_from_the_top(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    try:
        raise ValueError("x" * 200_000)
    except ValueError:
        logging.getLogger("myapp").exception("big")
    transport.flush()
    [error] = sent(ingest, "errors")
    assert len(error["stack"]) == 65_536
    assert len(error["message"]) == 2000
    for batch in ingest.batches():
        assert_valid("IngestBatch", batch)


# --- Events ---------------------------------------------------------------------


def test_event_props_and_user_ref(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    commandr.event("user.signup", user_id=42, plan="trial", seats=3, beta=True)
    commandr.event("user.signup", user_id=42)
    transport.flush()
    events = sent(ingest, "events")
    assert events[0]["props"]["plan"] == "trial"
    assert events[0]["props"]["seats"] == 3
    assert events[0]["props"]["beta"] is True
    assert "user_id" not in events[0]["props"]
    assert events[0]["props"]["user_ref"] == events[1]["props"]["user_ref"]
    assert "42" not in events[0]["props"]["user_ref"]
    assert events[0]["id"].startswith("evt_")


def test_personal_props_are_left_out(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    commandr.event(
        "user.signup", email="a@example.com", source="a@example.com", ip="1.2.3.4", plan="pro"
    )
    transport.flush()
    [event] = sent(ingest, "events")
    assert event["props"] == {"plan": "pro"}


def test_bad_event_name_is_dropped_not_raised(pushing: dict[str, Any], ingest: FakeIngest) -> None:
    commandr.event("User Signup")
    transport.flush()
    assert ingest.received == []


# --- Sending: retries, limits, never blocking ----------------------------------


def test_429_is_retried_with_the_same_idempotency_key(
    pushing: dict[str, Any], ingest: FakeIngest
) -> None:
    ingest.statuses = [429]
    commandr.event("user.signup")
    transport.flush()
    assert len(ingest.received) == 1
    transport._retry_at = 0  # skip the backoff
    transport.flush()
    first, second = ingest.received
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.body == second.body


def test_401_drops_the_batch_and_warns_once_a_minute(
    pushing: dict[str, Any], ingest: FakeIngest, caplog: pytest.LogCaptureFixture
) -> None:
    ingest.statuses = [401, 401]
    with caplog.at_level(logging.WARNING, logger="commandr_django"):
        for _ in range(2):
            commandr.event("user.signup")
            transport.flush()
    assert len(ingest.received) == 2
    warnings = [r for r in caplog.records if r.name == "commandr_django"]
    assert len(warnings) == 1
    assert "refused" in warnings[0].getMessage()
    assert pushing["INGEST_KEY"] not in warnings[0].getMessage()


def test_unreachable_server_never_raises(settings: Any, caplog: pytest.LogCaptureFixture) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": "http://127.0.0.1:9", "SEND_TIMEOUT": 1}
    commandr.event("user.signup")
    with caplog.at_level(logging.WARNING, logger="commandr_django"):
        transport.flush()
        transport._retry_at = 0
        transport.flush()
    warnings = [r for r in caplog.records if r.name == "commandr_django"]
    assert len(warnings) == 1  # once a minute, however many attempts


def test_buffer_is_bounded(settings: Any, ingest: FakeIngest) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url, "MAX_BUFFER": 5}
    for _ in range(20):
        commandr.event("user.signup")
    assert transport.pending()["events"] == 5


def test_enqueue_is_fast_while_the_server_hangs(settings: Any, ingest: FakeIngest) -> None:
    ingest.delay = 1.5
    settings.COMMANDR = {
        **settings.COMMANDR,
        "INGEST_URL": ingest.url,
        "FLUSH_INTERVAL": 0.01,
        "SEND_TIMEOUT": 1,
    }
    transport.ping(f"{ingest.url}/v1/heartbeat/x")  # wakes the sender: now stuck on it
    ingest.wait_for(1)
    started = time.monotonic()
    for _ in range(2000):
        commandr.event("user.signup")
    assert time.monotonic() - started < 0.5


def test_flush_gives_up_at_its_deadline(settings: Any, ingest: FakeIngest) -> None:
    ingest.delay = 1.5
    settings.COMMANDR = {
        **settings.COMMANDR,
        "INGEST_URL": ingest.url,
        "FLUSH_INTERVAL": 0.01,
        "SEND_TIMEOUT": 1,
    }
    transport.ping(f"{ingest.url}/v1/heartbeat/x")
    ingest.wait_for(1)
    commandr.event("user.signup")
    started = time.monotonic()
    commandr.flush(timeout=0.2)  # the thread holds the sender: do not wait for it
    assert time.monotonic() - started < 0.5


def test_big_batches_are_split(settings: Any, ingest: FakeIngest) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url, "MAX_BUFFER": 5000}
    for i in range(2500):
        commandr.event("user.signup", n=i)
    transport.flush()
    batches = ingest.batches()
    sizes = [len(b["events"]) for b in batches]
    assert max(sizes) <= 1000
    assert sum(sizes) == 2500
    for batch in batches:
        assert_valid("IngestBatch", batch)


def test_oversized_bodies_are_halved(
    settings: Any, ingest: FakeIngest, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url}
    monkeypatch.setattr(transport_module, "MAX_BODY", 2000)
    for i in range(40):
        commandr.event("user.signup", n=i)
    transport.flush()
    batches = ingest.batches()
    assert len(batches) > 1
    assert all(len(r.body) <= 2000 for r in ingest.received)
    assert sum(len(b["events"]) for b in batches) == 40


def test_redirects_are_not_followed(settings: Any, ingest: FakeIngest) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "INGEST_URL": ingest.url}
    ingest.statuses = [302]
    commandr.event("user.signup")
    transport.flush()
    assert len(ingest.received) == 1


# --- Heartbeats -----------------------------------------------------------------


@pytest.fixture
def beats(pushing: dict[str, Any], settings: Any, ingest: FakeIngest) -> FakeIngest:
    settings.COMMANDR = {
        **pushing,
        "HEARTBEATS": {
            "nightly-prune": "tok" + "1" * 40,
            "backup": f"{ingest.url}/v1/heartbeat/full",
        },
    }
    return ingest


def test_heartbeat_success(beats: FakeIngest) -> None:
    @commandr.heartbeat("nightly-prune")
    def prune() -> str:
        return "done"

    assert prune() == "done"
    received = beats.wait_for(2)
    token = "tok" + "1" * 40
    assert [r.path for r in received] == [f"/v1/heartbeat/{token}/start", f"/v1/heartbeat/{token}"]


def test_heartbeat_failure_reraises_and_reports(beats: FakeIngest) -> None:
    @commandr.heartbeat("backup")
    def backup() -> None:
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        backup()
    received = beats.wait_for(2)
    assert [r.path for r in received] == ["/v1/heartbeat/full/start", "/v1/heartbeat/full/fail"]
    assert received[1].body == b"OSError: disk full"


def test_async_heartbeat(beats: FakeIngest) -> None:
    @commandr.heartbeat("backup")
    async def backup() -> int:
        return 7

    assert asyncio.run(backup()) == 7
    assert [r.path for r in beats.wait_for(2)] == ["/v1/heartbeat/full/start", "/v1/heartbeat/full"]


def test_unknown_heartbeat_runs_the_job_anyway(beats: FakeIngest) -> None:
    @commandr.heartbeat("not-configured")
    def job() -> int:
        return 1

    assert job() == 1
    time.sleep(0.2)
    assert beats.received == []


def test_heartbeat_does_not_wait_for_commandr(settings: Any, ingest: FakeIngest) -> None:
    ingest.delay = 1.5
    settings.COMMANDR = {
        **settings.COMMANDR,
        "INGEST_URL": ingest.url,
        "SEND_TIMEOUT": 1,
        "HEARTBEATS": {"job": "tok" + "2" * 40},
    }

    @commandr.heartbeat("job")
    def job() -> None:
        pass

    started = time.monotonic()
    job()
    assert time.monotonic() - started < 0.2
