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


# --- Phase 1 fixtures ----------------------------------------------------------

PUBLIC_IP = "93.184.215.14"


@pytest.fixture
def fresh_api(api: APIClient):  # type: ignore[no-untyped-def]
    """An API client signed in through a real session with a recent
    authentication record, as after typing the password (reauth checks)."""
    import time

    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY

    def login(user):  # type: ignore[no-untyped-def]
        api.force_login(user)
        session = api.session
        session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": time.time()}]
        session.save()
        return api

    return login


@pytest.fixture
def fake_stream(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The ingest stream on fakeredis."""
    import fakeredis

    from commandr.ingest import stream

    client = fakeredis.FakeRedis()
    monkeypatch.setattr(stream, "get_client", lambda: client)
    return client


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Every name resolves to one public address, unless overridden in `mapping`."""
    import socket

    mapping: dict[str, list[str]] = {}

    def getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        ips = mapping.get(host, [PUBLIC_IP])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return mapping


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, public_dns):  # type: ignore[no-untyped-def]
    """Route every egress fetch to `http.handler` (an httpx MockTransport handler)."""
    import httpx

    from commandr.core.safe_http import SafeHttpClient
    from commandr.monitoring import tasks

    class Router:
        requests: list[httpx.Request]

        def __init__(self) -> None:
            self.requests = []
            self.handler = lambda request: httpx.Response(200, text="ok")

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

    router = Router()
    monkeypatch.setattr(
        tasks,
        "make_client",
        lambda **kw: SafeHttpClient(transport=httpx.MockTransport(router), **kw),
    )
    return router


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Rate limits, idempotency answers and credential lookups live in the cache."""
    from django.core.cache import cache

    cache.clear()
