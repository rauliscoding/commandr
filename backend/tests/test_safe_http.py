"""SSRF protection for customer-supplied URLs (security.md § Outbound HTTP)."""

import socket

import httpx
import pytest

from commandr.core.safe_http import (
    DisallowedDestination,
    ResponseTooLarge,
    SafeHttpClient,
    SafeHttpError,
)

PUBLIC_IP = "93.184.215.14"


def fake_dns(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    def getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host not in mapping:
            raise socket.gaierror("unknown")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in mapping[host]]

    return getaddrinfo


def client(handler, **kwargs) -> SafeHttpClient:  # type: ignore[no-untyped-def]
    return SafeHttpClient(transport=httpx.MockTransport(handler), **kwargs)


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"host": request.headers["host"], "url": str(request.url)})


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "https://10.0.0.5/",
        "https://192.168.1.1/",
        "https://172.16.0.1/",
        "https://100.64.0.1/",  # CGNAT
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://[::1]/",
        "https://[fd00:ec2::254]/",
        "https://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
        "https://0.0.0.0/",
    ],
)
def test_refuses_non_public_ip_literals(url: str) -> None:
    with pytest.raises(DisallowedDestination):
        client(ok).get(url)


def test_refuses_names_resolving_to_private_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"internal.example": ["10.1.2.3"]}))
    with pytest.raises(DisallowedDestination):
        client(ok).get("https://internal.example/")


def test_refuses_when_any_resolved_address_is_private(monkeypatch: pytest.MonkeyPatch) -> None:
    """One public and one private record must not let the private one through."""
    monkeypatch.setattr(
        socket, "getaddrinfo", fake_dns({"mixed.example": [PUBLIC_IP, "127.0.0.1"]})
    )
    with pytest.raises(DisallowedDestination):
        client(ok).get("https://mixed.example/")


def test_refuses_http_unless_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))
    with pytest.raises(DisallowedDestination):
        client(ok).get("http://site.example/")
    assert client(ok, allow_http=True).get("http://site.example/").status_code == 200


def test_refuses_other_schemes_and_embedded_credentials() -> None:
    with pytest.raises(DisallowedDestination):
        client(ok).get("file:///etc/passwd")
    with pytest.raises(SafeHttpError):
        client(ok).get("https://user:pass@site.example/")


def test_connects_to_the_pinned_ip_with_original_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["host"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    response = client(handler).get("https://site.example/.well-known/commandr/status?x=1")
    assert response.status_code == 200
    assert response.resolved_ip == PUBLIC_IP
    assert seen["url"] == f"https://{PUBLIC_IP}/.well-known/commandr/status?x=1"
    assert seen["host"] == "site.example"
    assert seen["sni"] == "site.example"


def test_redirects_are_not_followed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://site.example/next"})

    assert client(handler).get("https://site.example/").status_code == 302


def test_each_redirect_hop_is_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_dns({"site.example": [PUBLIC_IP], "evil.example": ["169.254.169.254"]}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/latest"})

    with pytest.raises(DisallowedDestination):
        client(handler, max_redirects=3).get("https://site.example/")


def test_follows_allowed_redirects_up_to_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/final":
            return httpx.Response(200, text="done")
        return httpx.Response(301, headers={"location": "/final"})

    response = client(handler, max_redirects=1).get("https://site.example/start")
    assert response.status_code == 200
    assert response.redirects == ["https://site.example/start"]


def test_caps_response_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2_000)

    with pytest.raises(ResponseTooLarge):
        client(handler, max_bytes=1_000).get("https://site.example/")


def test_timeouts_become_safe_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", fake_dns({"site.example": [PUBLIC_IP]}))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(SafeHttpError, match="timed out"):
        client(handler).get("https://site.example/")
