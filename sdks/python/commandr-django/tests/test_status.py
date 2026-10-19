"""The signed status endpoint: signature, document, contract."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from django.test import Client

import commandr_django as commandr
from commandr_django import status

from .conftest import SECRET, assert_valid, server_signing

PATH = "/.well-known/commandr/status"
PROJECT = "prj_" + "0" * 31 + "1"

pytestmark = pytest.mark.django_db(transaction=True)


def signed_get(
    client: Client,
    path: str = PATH,
    *,
    secret: str = SECRET,
    at: int | None = None,
    method: str = "GET",
    **headers: str,
) -> Any:
    signing = server_signing()
    header = signing.sign(secret, method, signing.signed_path(path), at or int(time.time()))
    return client.generic(
        method,
        path,
        headers={"X-Commandr-Signature": header, "X-Commandr-Project": PROJECT, **headers},
    )


def checks_by_key(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in document["checks"]}


# --- Signature ------------------------------------------------------------------


def test_signed_request_gets_a_valid_document(client: Client) -> None:
    response = signed_get(client)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Cache-Control"] == "no-store"
    document = response.json()
    assert_valid("StatusDocument", document)
    assert document["service"] == "testproject"
    assert document["version"] == "1.2.0"
    assert document["environment"] == "test"


def test_query_string_is_not_signed(client: Client) -> None:
    signing = server_signing()
    header = signing.sign(SECRET, "GET", signing.signed_path(PATH + "?x=1"), int(time.time()))
    response = client.get(PATH + "?x=1", headers={"X-Commandr-Signature": header})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Commandr-Signature": ""},
        {"X-Commandr-Signature": "garbage"},
        {"X-Commandr-Signature": "t=abc,v1=00"},
        {"X-Commandr-Signature": "t=1,v1=" + "0" * 64},
        {"X-Commandr-Signature": "t=1760600000,v1=é"},
    ],
)
def test_missing_or_malformed_signature_is_401_with_no_detail(
    client: Client, headers: dict[str, str]
) -> None:
    response = client.get(PATH, headers=headers)
    assert response.status_code == 401
    assert response.content == b""


def test_wrong_secret_is_401(client: Client) -> None:
    response = signed_get(client, secret="another-secret")
    assert response.status_code == 401
    assert response.content == b""


@pytest.mark.parametrize(("skew", "ok"), [(-299, True), (299, True), (-301, False), (301, False)])
def test_timestamp_tolerance_is_300_seconds(client: Client, skew: int, ok: bool) -> None:
    response = signed_get(client, at=int(time.time()) + skew)
    assert (response.status_code == 200) is ok


def test_signature_for_another_path_is_refused(client: Client) -> None:
    signing = server_signing()
    header = signing.sign(SECRET, "GET", "/somewhere-else", int(time.time()))
    response = client.get(PATH, headers={"X-Commandr-Signature": header})
    assert response.status_code == 401


def test_signature_for_another_method_is_refused(client: Client) -> None:
    signing = server_signing()
    header = signing.sign(SECRET, "POST", PATH, int(time.time()))
    assert client.get(PATH, headers={"X-Commandr-Signature": header}).status_code == 401


def test_post_is_not_allowed(client: Client) -> None:
    assert signed_get(client, method="POST").status_code == 405


def test_no_secret_configured_is_401(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "SIGNING_SECRET": ""}
    assert signed_get(client).status_code == 401


def test_project_is_checked_when_configured(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "PROJECT": PROJECT}
    assert signed_get(client).status_code == 200
    settings.COMMANDR = {**settings.COMMANDR, "PROJECT": "prj_" + "f" * 32}
    assert signed_get(client).status_code == 401


def test_checks_do_not_run_for_an_unsigned_request(client: Client) -> None:
    ran = []

    @commandr.check("expensive")
    def expensive() -> bool:
        ran.append(1)
        return True

    client.get(PATH)
    assert ran == []


def test_etag_answers_304_when_nothing_changed(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "BUILTINS": ["database", "cache"]}
    first = signed_get(client)
    tag = first["ETag"]
    second = signed_get(client, **{"If-None-Match": tag})
    assert second.status_code == 304
    assert second["ETag"] == tag


# --- Built-in checks ------------------------------------------------------------


def test_builtin_checks(client: Client) -> None:
    checks = checks_by_key(signed_get(client).json())
    assert checks["database"]["status"] == "ok"
    assert checks["database"]["name"] == "SQLite"
    assert checks["cache"]["status"] == "ok"
    assert checks["disk"]["status"] in ("ok", "warn", "fail")
    assert 0 <= checks["disk"]["value"] <= 1
    assert checks["disk"]["unit"] == "ratio"
    assert " GB" in checks["disk"]["summary"]


def test_builtins_can_be_chosen(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "BUILTINS": ["database"]}
    document = signed_get(client).json()
    assert [c["key"] for c in document["checks"]] == ["database"]
    assert document["gauges"] == []


def test_missing_disk_fails(client: Client, settings: Any) -> None:
    settings.COMMANDR = {
        **settings.COMMANDR,
        "BUILTINS": ["disk"],
        "DISK_PATHS": {"Root": "/", "External": "/no/such/volume"},
    }
    checks = checks_by_key(signed_get(client).json())
    assert set(checks) == {"disk", "disk:External"}
    assert checks["disk:External"]["status"] == "fail"


def test_database_down_fails_without_leaking_the_message(client: Client, settings: Any) -> None:
    def broken(alias: str) -> None:
        raise ConnectionError("could not connect to db.internal:5432 as admin/hunter2")

    from commandr_django import builtin

    original = builtin.database
    builtin.database = broken  # type: ignore[assignment]
    try:
        checks = checks_by_key(signed_get(client).json())
    finally:
        builtin.database = original
    assert checks["database"] == {
        "key": "database",
        "name": "SQLite",
        "status": "fail",
        "summary": "raised ConnectionError",
    }


def test_celery_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    from commandr_django import builtin
    from commandr_django.conf import get_config

    class Control:
        def __init__(self, replies: list[Any]) -> None:
            self.replies = replies

        def ping(self, timeout: float) -> list[Any]:
            return self.replies

    class App:
        main = "proj"

        def __init__(self, replies: list[Any]) -> None:
            self.control = Control(replies)

    config = get_config()
    monkeypatch.setattr(builtin, "celery_app", lambda c: App([{"w1": {"ok": "pong"}}]))
    assert builtin.celery_workers(config) == commandr.Check.ok("1 worker answered")
    monkeypatch.setattr(builtin, "celery_app", lambda c: App([]))
    assert builtin.celery_workers(config).status == "fail"


def test_no_celery_app_means_no_celery_check(client: Client) -> None:
    # Celery is not installed in the test environment, and none is configured.
    assert "celery" not in checks_by_key(signed_get(client).json())


# --- The app's own checks, KPIs and gauges --------------------------------------


def test_custom_checks_kpis_and_gauges(client: Client) -> None:
    @commandr.check("disk:External", name="External volume")
    def external() -> commandr.Check:
        return commandr.Check.from_ratio(0.862, warn=0.85, fail=0.95, summary="86.2 / 100 GB")

    @commandr.check("payments")
    def payments() -> bool:
        return False

    @commandr.kpi("user.total", label="Users", unit="count")
    def users() -> int:
        return 412

    @commandr.kpi("revenue.mrr", label="MRR", unit="EUR")
    def mrr() -> None:
        return None

    @commandr.gauge("queue.depth", attrs={"queue": "celery"})
    def depth() -> int:
        return 3

    document = signed_get(client).json()
    assert_valid("StatusDocument", document)
    checks = checks_by_key(document)
    assert checks["disk:External"] == {
        "key": "disk:External",
        "name": "External volume",
        "status": "warn",
        "summary": "86.2 / 100 GB",
        "value": 0.862,
        "unit": "ratio",
    }
    assert checks["payments"]["status"] == "fail"
    kpis = {k["name"]: k for k in document["kpis"]}
    assert kpis["user.total"] == {
        "name": "user.total",
        "label": "Users",
        "value": 412,
        "unit": "count",
    }
    assert kpis["revenue.mrr"]["value"] is None  # not available: "—", never 0
    assert {"name": "queue.depth", "value": 3, "attrs": {"queue": "celery"}} in document["gauges"]


def test_app_check_replaces_builtin_with_same_key(client: Client) -> None:
    @commandr.check("database", name="Primary DB")
    def db() -> commandr.Check:
        return commandr.Check.warn("replica lag 30 s")

    checks = checks_by_key(signed_get(client).json())
    assert checks["database"]["name"] == "Primary DB"
    assert checks["database"]["status"] == "warn"


def test_failing_kpi_is_null_never_zero(client: Client) -> None:
    @commandr.kpi("user.total")
    def broken() -> int:
        raise RuntimeError("database gone")

    document = signed_get(client).json()
    assert document["kpis"] == [{"name": "user.total", "value": None}]


@pytest.mark.parametrize(
    ("returned", "expected"),
    [
        (True, {"status": "ok"}),
        (None, {"status": "unknown", "summary": "no result"}),
        ("yes", {"status": "unknown", "summary": "the check returned something else"}),
        (
            commandr.Check("bad"),  # type: ignore[arg-type]
            {"status": "unknown", "summary": "the check returned something else"},
        ),
        (commandr.Check.ok(value=float("nan")), {"status": "ok"}),
    ],
)
def test_odd_check_results_stay_valid(
    client: Client, returned: Any, expected: dict[str, Any]
) -> None:
    @commandr.check("odd")
    def odd() -> Any:
        return returned

    document = signed_get(client).json()
    assert_valid("StatusDocument", document)
    entry = checks_by_key(document)["odd"]
    assert {k: v for k, v in entry.items() if k not in ("key", "name")} == expected


def test_bad_names_are_ignored_not_raised() -> None:
    @commandr.kpi("Users Total")
    def bad() -> int:
        return 1

    @commandr.gauge("queue depth")
    def bad_gauge() -> int:
        return 1

    from commandr_django import registry

    assert registry.kpis() == []
    assert registry.gauges() == []


def test_slow_check_fails_without_delaying_the_answer(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "CHECK_TIMEOUT": 0.3, "BUILTINS": []}
    release = threading.Event()

    @commandr.check("slow")
    def slow() -> bool:
        release.wait(5)
        return True

    @commandr.kpi("slow.kpi")
    def slow_kpi() -> int:
        release.wait(5)
        return 1

    try:
        started = time.monotonic()
        document = signed_get(client).json()
        assert time.monotonic() - started < 2
        assert checks_by_key(document)["slow"] == {
            "key": "slow",
            "name": "slow",
            "status": "fail",
            "summary": "did not finish within 0.3 s",
        }
        assert document["kpis"] == [{"name": "slow.kpi", "value": None}]
        # Still stuck at the next poll: not started a second time.
        again = checks_by_key(signed_get(client).json())["slow"]
        assert again["summary"] == "still running since an earlier poll"
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and status._running:
        time.sleep(0.02)
    assert checks_by_key(signed_get(client).json())["slow"]["status"] == "ok"


def test_limits_are_respected(client: Client, settings: Any) -> None:
    settings.COMMANDR = {**settings.COMMANDR, "BUILTINS": []}
    for i in range(status.MAX_KPIS + 5):
        commandr.kpi(f"k.n{i}")(lambda: 1)
    document = signed_get(client).json()
    assert len(document["kpis"]) == status.MAX_KPIS
    assert_valid("StatusDocument", document)


def test_long_text_is_truncated_to_the_contract(client: Client) -> None:
    @commandr.check("k" * 300, name="n" * 300)
    def too_long_key() -> bool:  # ignored: key over 200
        return True

    @commandr.check("long")
    def long() -> commandr.Check:
        return commandr.Check("ok", "s" * 900, 1, "u" * 50)

    document = signed_get(client).json()
    assert_valid("StatusDocument", document)
    assert "k" * 300 not in checks_by_key(document)
