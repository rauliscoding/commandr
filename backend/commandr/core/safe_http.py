"""Fetching URLs that customers typed, without becoming an SSRF hole.

Every request to a customer-supplied URL (status endpoints, uptime probes,
webhooks, media downloads) MUST go through `SafeHttpClient`. It:

1. accepts only allowed schemes (https; http only when the caller opts in);
2. resolves DNS **once** and refuses if ANY resolved address is not globally
   routable (private, loopback, link-local, CGNAT, multicast, reserved…) or is a
   cloud metadata address;
3. connects to the **pinned** IP it validated — with the Host header and TLS SNI
   set to the original name, so certificates still verify — closing the
   DNS-rebinding window between "check" and "connect";
4. never follows redirects automatically; each hop is re-validated, max 3;
5. caps total time and response size.

See docs/practices/security.md § Outbound HTTP and SSRF.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings

_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),  # AWS, GCP, Azure, Hetzner, DO
    ipaddress.ip_address("fd00:ec2::254"),  # AWS IPv6
}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class SafeHttpError(Exception):
    """A request was refused or failed. The message is safe to show the customer."""


class DisallowedDestination(SafeHttpError):
    pass


class ResponseTooLarge(SafeHttpError):
    pass


@dataclass(frozen=True)
class SafeResponse:
    status_code: int
    headers: httpx.Headers
    content: bytes
    url: str
    resolved_ip: str
    redirects: list[str] = field(default_factory=list)
    # When the server's TLS certificate expires (https only; None if unknown).
    tls_not_after: datetime | None = None

    def json(self) -> object:
        import json

        return json.loads(self.content)


def _is_allowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip in _METADATA_ADDRESSES:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_allowed_ip(ip.ipv4_mapped)
    # is_global is False for private, loopback, link-local, CGNAT (100.64/10),
    # unique-local, documentation and reserved ranges.
    return ip.is_global and not ip.is_multicast


def resolve_and_validate(host: str, port: int) -> str:
    """Resolve `host` and return one address to connect to, or raise."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_allowed_ip(literal):
            raise DisallowedDestination("That address is not reachable from Commandr.")
        return str(literal)

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SafeHttpError(f"Could not resolve {host}.") from exc
    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses:
        raise SafeHttpError(f"Could not resolve {host}.")
    # ALL must be allowed: otherwise a name with one public and one private
    # record could be steered to the private one.
    if not all(_is_allowed_ip(a) for a in addresses):
        raise DisallowedDestination(
            f"{host} resolves to an address that is not reachable from Commandr."
        )
    # Prefer IPv4 for predictability; any validated address is acceptable.
    return str(sorted(addresses, key=lambda a: (a.version, int(a)))[0])


class SafeHttpClient:
    """Bounded HTTP client for customer-supplied URLs.

    `transport` exists for tests (httpx.MockTransport); production uses the
    default transport.
    """

    def __init__(
        self,
        *,
        allow_http: bool = False,
        max_redirects: int = 0,
        connect_timeout: float = 5.0,
        total_timeout: float = 15.0,
        max_bytes: int = 1_000_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.allowed_schemes = {"https", "http"} if allow_http else {"https"}
        self.max_redirects = min(max_redirects, 3)
        self.max_bytes = max_bytes
        self._client = httpx.Client(
            timeout=httpx.Timeout(total_timeout, connect=connect_timeout),
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": settings.SAFE_HTTP_USER_AGENT},
        )

    def __enter__(self) -> SafeHttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None
    ) -> SafeResponse:
        hops: list[str] = []
        current = url
        for _ in range(self.max_redirects + 1):
            response, ip, tls_not_after = self._one(method, current, headers or {})
            follow = self.max_redirects > 0
            if (
                follow
                and response.status_code in _REDIRECT_CODES
                and "location" in response.headers
            ):
                if len(hops) >= self.max_redirects:
                    raise SafeHttpError("Too many redirects.")
                hops.append(current)
                current = urljoin(current, response.headers["location"])
                if response.status_code == 303:
                    method = "GET"
                continue
            return SafeResponse(
                status_code=response.status_code,
                headers=response.headers,
                content=response.content,
                url=current,
                resolved_ip=ip,
                redirects=hops,
                tls_not_after=tls_not_after,
            )
        raise SafeHttpError("Too many redirects.")

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> SafeResponse:
        return self.request("GET", url, headers=headers)

    def _one(
        self, method: str, url: str, headers: dict[str, str]
    ) -> tuple[httpx.Response, str, datetime | None]:
        parts = urlsplit(url)
        if parts.scheme not in self.allowed_schemes:
            raise DisallowedDestination("Only https:// addresses are allowed here.")
        if not parts.hostname:
            raise SafeHttpError("That address has no host name.")
        if parts.username or parts.password:
            raise SafeHttpError("Addresses with embedded credentials are not allowed.")
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "https" else 80)
        ip = resolve_and_validate(host, port)

        ip_host = f"[{ip}]" if ":" in ip else ip
        netloc = ip_host if parts.port is None else f"{ip_host}:{parts.port}"
        pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
        host_header = host if parts.port is None else f"{host}:{parts.port}"

        request = self._client.build_request(
            method,
            pinned,
            headers={**headers, "Host": host_header},
            # TLS server name = the original host, so the certificate is
            # verified against the name the customer gave, not the IP.
            extensions={"sni_hostname": host},
        )
        try:
            response = self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise SafeHttpError("The request timed out.") from exc
        except httpx.HTTPError as exc:
            raise SafeHttpError("Could not connect.") from exc
        tls_not_after = _peer_cert_expiry(response)
        try:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self.max_bytes:
                    raise ResponseTooLarge(
                        f"The response is larger than {self.max_bytes // 1000} KB."
                    )
        finally:
            response.close()
        response._content = bytes(body)
        return response, ip, tls_not_after


def _peer_cert_expiry(response: httpx.Response) -> datetime | None:
    """The verified peer certificate's notAfter, read while the stream is open."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return None
    ssl_object = stream.get_extra_info("ssl_object")
    if not isinstance(ssl_object, ssl.SSLObject | ssl.SSLSocket):
        return None
    cert = ssl_object.getpeercert()
    not_after = cert.get("notAfter") if cert else None
    if not isinstance(not_after, str):
        return None
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=UTC)
