"""Credential → tenant, without a cross-tenant query (ADR 0008)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.core.cache import cache

from .keys import digest
from .models import CredentialKind, CredentialLookup

_TTL = 60
_MISS = "-"


@dataclass(frozen=True)
class Found:
    organization_id: UUID
    target_id: UUID


def _cache_key(d: str) -> str:
    return f"ingest:cred:{d}"


def find(credential: str, kind: CredentialKind) -> Found | None:
    """Resolve a presented credential. Cached briefly, misses included, so a
    flood of bad keys costs one cache read each, not one query each."""
    d = digest(credential)
    cached = cache.get(_cache_key(d))
    if cached == _MISS:
        return None
    if cached is not None:
        cached_kind, org, target = cached.split(":")
        return Found(UUID(org), UUID(target)) if cached_kind == kind else None
    row = (
        CredentialLookup.objects.filter(digest=d)
        .values_list("kind", "organization_id", "target_id")
        .first()
    )
    if row is None:
        cache.set(_cache_key(d), _MISS, _TTL)
        return None
    cache.set(_cache_key(d), f"{row[0]}:{row[1]}:{row[2]}", _TTL)
    return Found(row[1], row[2]) if row[0] == kind else None


def add(
    *, credential_digest: str, kind: CredentialKind, organization_id: UUID, target_id: UUID
) -> None:
    CredentialLookup.objects.create(
        digest=credential_digest, kind=kind, organization_id=organization_id, target_id=target_id
    )
    cache.delete(_cache_key(credential_digest))


def remove(credential_digest: str) -> None:
    """Revocation: effective immediately, cache included."""
    CredentialLookup.objects.filter(digest=credential_digest).delete()
    cache.delete(_cache_key(credential_digest))
