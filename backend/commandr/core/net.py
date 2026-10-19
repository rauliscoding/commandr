"""Who is calling: the client address, behind Caddy or not."""

import ipaddress
from functools import lru_cache

from django.conf import settings
from django.http import HttpRequest


@lru_cache(maxsize=8)
def _trusted(cidrs: tuple[str, ...]) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def client_ip(request: HttpRequest) -> str | None:
    """The caller's IP address.

    `X-Forwarded-For` is believed only when the direct peer is a trusted proxy
    (`TRUSTED_PROXY_CIDRS`), and then only its right-most entry: that is the
    one Caddy appended itself. Anything to the left was sent by the client and
    could be forged (CLAUDE.md invariant 4).
    """
    peer = request.META.get("REMOTE_ADDR") or None
    if peer is None:
        return None
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return None
    networks = _trusted(tuple(settings.TRUSTED_PROXY_CIDRS))
    if networks and any(peer_ip in n for n in networks):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        last = forwarded.split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(last))
        except ValueError:
            return str(peer_ip)
    return str(peer_ip)
